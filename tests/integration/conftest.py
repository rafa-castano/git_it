"""Shared fixtures for integration tests.

All integration tests use a real SQLite temp DB with:
- No internet access — git clone/fetch is mocked at the SafeGitGateway level.
- No LLM calls — analysis is not triggered in the lifecycle tests.
- Background ingest thread runs synchronously so DB state is visible immediately.

Threading strategy
------------------
repos.py does ``import threading`` and then calls ``threading.Thread(...)``.
We replace the ``threading`` name in *that module's namespace only* (via
``monkeypatch.setattr(repos_module, "threading", ...)``) with a fake module
whose ``Thread`` class runs the target synchronously in ``start()``.

This avoids patching the global ``threading`` module, which would break
Starlette's TestClient infrastructure (it relies on real OS threads to run the
ASGI app in the background during requests).

Table initialisation strategy
------------------------------
``build_repository_ingestion_service`` only creates ``ingestion_runs``,
``commit_facts``, and ``file_facts`` tables.  Read endpoints such as
``GET /api/repos`` do LEFT JOINs against ``commit_analyses`` and
``case_studies``, which SQLite requires to exist.  The fixture pre-initialises
ALL tables before creating the app so every subsequent request finds a
consistent schema.
"""

import threading as _real_threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from git_it.repository_ingestion.domain.commits import ExtractedCommit, ExtractedFileChange
from git_it.repository_ingestion.infrastructure.sqlite import (
    SqliteCaseStudyStore,
    SqliteCommitAnalysisStore,
    SqliteCommitFactStore,
    SqliteFileFactStore,
    SqliteIngestionRunStore,
)
from git_it.repository_ingestion.infrastructure.workspace import ingestion_workspace_root

# ---------------------------------------------------------------------------
# Deterministic fake commits returned by the mocked extractor
# ---------------------------------------------------------------------------

FAKE_COMMITS: list[ExtractedCommit] = [
    ExtractedCommit(
        sha="abc123def456abc123def456abc123def456abc1",
        committed_at="2024-01-15T10:00:00",
        message="feat: add authentication module",
        author_name="Alice",
        committer_name="Alice",
        parent_shas=(),
        file_changes=(ExtractedFileChange(path="src/auth.py", insertions=50, deletions=0),),
        author_email="alice@example.com",
    ),
    ExtractedCommit(
        sha="def789abc012def789abc012def789abc012def7",
        committed_at="2024-01-16T10:00:00",
        message="fix: resolve null pointer in auth",
        author_name="Bob",
        committer_name="Bob",
        parent_shas=("abc123def456abc123def456abc123def456abc1",),
        file_changes=(ExtractedFileChange(path="src/auth.py", insertions=5, deletions=2),),
        author_email="bob@example.com",
    ),
]


# ---------------------------------------------------------------------------
# Synchronous thread replacement (module-local, not global)
# ---------------------------------------------------------------------------


class _SyncThread:
    """Drop-in replacement for threading.Thread that runs synchronously.

    ``start()`` calls the target function directly in the current thread
    instead of spawning a new OS thread.  This ensures that after the
    ingest HTTP call returns, all DB writes are already visible.
    """

    def __init__(
        self,
        *,
        target: Any = None,
        args: tuple = (),
        kwargs: dict | None = None,
        daemon: bool | None = None,
        **_: Any,
    ) -> None:
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target is not None:
            self._target(*self._args, **self._kwargs)

    def run(self) -> None:
        self.start()


# Fake threading namespace exposed to repos.py.
# Preserves Lock so any module-level lock creation still works.
_FAKE_THREADING = type(
    "_FakeThreading",
    (),
    {
        "Thread": _SyncThread,
        "Lock": _real_threading.Lock,
    },
)()


# ---------------------------------------------------------------------------
# Helper: pre-initialise the full DB schema
# ---------------------------------------------------------------------------


def _init_full_schema(db_path: Path) -> None:
    """Create all tables the read endpoints rely on.

    ``build_repository_ingestion_service`` only creates three of the five
    tables.  The two remaining ones (``commit_analyses``, ``case_studies``)
    are created here so that LEFT JOINs in the list-repos query succeed.
    """
    SqliteIngestionRunStore(db_path).initialize()
    SqliteCommitFactStore(db_path).initialize()
    SqliteFileFactStore(db_path).initialize()
    SqliteCommitAnalysisStore(db_path).initialize()
    SqliteCaseStudyStore(db_path).initialize()


# ---------------------------------------------------------------------------
# Fixture: wired-up TestClient with mocked git + real SQLite
# ---------------------------------------------------------------------------


@pytest.fixture()
def integration_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    """Return a TestClient wired against a real SQLite temp DB.

    Four things are configured:
    1. Full DB schema — all five tables created before the app starts.
    2. ``repos_module.threading`` — replaced with a namespace whose Thread runs
       synchronously.  Scoped to the repos module only; TestClient's internal
       OS threads are unaffected.
    3. SafeGitGateway.clone_or_fetch — no-op; no network or subprocess.
    4. GitPythonCommitExtractor.extract_commits — returns FAKE_COMMITS; no
       actual git repo on disk is required.

    Everything else (DB writes, ingestion run records, commit fact writes,
    file fact writes, pattern detection, contributor aggregation) runs for real.
    """
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    # (1) Pre-initialise the full schema before any request touches the DB.
    db_path = ingestion_workspace_root(tmp_path) / "git-it.sqlite3"
    _init_full_schema(db_path)

    # (2) Replace threading in repos.py with a synchronous equivalent.
    #     Uses module-local patching so TestClient threads are unaffected.
    monkeypatch.setattr(repos_module, "threading", _FAKE_THREADING)

    # (3) No-op the git clone/fetch — the only step that needs a network.
    monkeypatch.setattr(
        "git_it.repository_ingestion.infrastructure.git.SafeGitGateway.clone_or_fetch",
        lambda self, url: None,
    )

    # (4) Return deterministic fake commits without touching a git bare repo.
    monkeypatch.setattr(
        "git_it.repository_ingestion.infrastructure.commits.GitPythonCommitExtractor.extract_commits",
        lambda self, skip_shas=frozenset(): FAKE_COMMITS,
    )

    # (5) Reset the shared in-memory rate limiter before and after each test.
    #     The ingest endpoint has a 5/minute limit; without this, integration
    #     tests would 429 after the 5th call, and leaking counter state into
    #     the unit test suite would break existing tests there too.
    from git_it.api.limiter import limiter

    def _reset_limiter() -> None:
        try:
            limiter._storage.reset()
        except Exception:
            pass  # Defensive: skip if storage type doesn't support reset

    _reset_limiter()

    app = create_app(project_root=tmp_path)
    yield TestClient(app)

    _reset_limiter()  # teardown: leave limiter clean for subsequent tests
