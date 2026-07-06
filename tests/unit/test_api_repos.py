"""Tests for the Git It REST API — Batch 47.

All tests use FastAPI's TestClient with a temporary SQLite DB.
No network, no external services, fully deterministic.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_path(tmp_path: Path) -> Path:
    data_dir = tmp_path / ".data" / "git-it" / "ingestion"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "git-it.sqlite3"


def _init_db(db: Path) -> None:
    """Create all tables needed by the API routes."""
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                run_id TEXT PRIMARY KEY,
                repository_id TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                error_code TEXT,
                error_stage TEXT,
                retryable INTEGER,
                safe_message TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS commit_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id TEXT NOT NULL,
                sha TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                message TEXT NOT NULL,
                author_name TEXT NOT NULL,
                committer_name TEXT NOT NULL,
                parent_shas TEXT NOT NULL,
                UNIQUE(repository_id, sha)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS commit_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(repository_id, commit_sha)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_studies (
                repository_id TEXT PRIMARY KEY,
                narrative TEXT NOT NULL,
                commit_count INTEGER NOT NULL,
                hotspot_count INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                file_path TEXT NOT NULL,
                insertions INTEGER NOT NULL,
                deletions INTEGER NOT NULL,
                UNIQUE(repository_id, commit_sha, file_path)
            )
            """
        )


def _insert_ingestion_run(
    db: Path,
    *,
    run_id: str = "run-1",
    repository_id: str = "repo-abc",
    canonical_url: str = "https://github.com/test/repo",
    status: str = "COMPLETED",
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO ingestion_runs (run_id, repository_id, canonical_url, status, started_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (run_id, repository_id, canonical_url, status, "2024-01-01T00:00:00"),
        )


def _insert_commit(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    sha: str = "aaa111",
    committed_at: str = "2024-01-01T10:00:00",
    message: str = "feat: first commit",
    author_name: str = "Alice",
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO commit_facts"
            " (repository_id, sha, committed_at, message, author_name, committer_name, parent_shas)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (repository_id, sha, committed_at, message, author_name, author_name, "[]"),
        )


def _insert_analysis(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    commit_sha: str = "aaa111",
    category: str = "feature",
    importance: str = "high",
    summary: str = "Added feature X",
) -> None:
    data = json.dumps(
        {
            "commit_sha": commit_sha,
            "summary": summary,
            "category": category,
            "importance": importance,
            "confidence": 0.9,
            "risk_level": "low",
            "affected_components": [],
            "evidence": [],
            "limitations": [],
        }
    )
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO commit_analyses (repository_id, commit_sha, data)"
            " VALUES (?, ?, ?)",
            (repository_id, commit_sha, data),
        )


def _insert_file_fact(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    commit_sha: str = "aaa111",
    file_path: str = "src/main.py",
    insertions: int = 10,
    deletions: int = 5,
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO file_facts"
            " (repository_id, commit_sha, file_path, insertions, deletions)"
            " VALUES (?, ?, ?, ?, ?)",
            (repository_id, commit_sha, file_path, insertions, deletions),
        )


def _insert_case_study(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    narrative: str = "# Case Study\n\nThis is the narrative.",
    commit_count: int = 5,
    hotspot_count: int = 2,
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO case_studies (repository_id, narrative, commit_count, hotspot_count)"
            " VALUES (?, ?, ?, ?)",
            (repository_id, narrative, commit_count, hotspot_count),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client_empty(tmp_path: Path) -> TestClient:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    app = create_app(project_root=tmp_path)
    return TestClient(app)


@pytest.fixture()
def client_with_repo(tmp_path: Path) -> TestClient:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    app = create_app(project_root=tmp_path)
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/repos — empty DB
# ---------------------------------------------------------------------------


def test_list_repos_empty_returns_200(client_empty: TestClient) -> None:
    response = client_empty.get("/api/repos")
    assert response.status_code == 200


def test_list_repos_empty_returns_empty_list(client_empty: TestClient) -> None:
    response = client_empty.get("/api/repos")
    body = response.json()
    assert body["repos"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/repos — with data
# ---------------------------------------------------------------------------


def test_list_repos_returns_ingested_repo(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(
        db,
        repository_id="repo-abc",
        canonical_url="https://github.com/test/repo",
        status="COMPLETED",
    )
    _insert_commit(db, repository_id="repo-abc", sha="aaa111")
    _insert_commit(db, repository_id="repo-abc", sha="bbb222", committed_at="2024-01-02T10:00:00")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    repo = body["repos"][0]
    assert repo["repository_id"] == "repo-abc"
    assert repo["canonical_url"] == "https://github.com/test/repo"
    assert repo["status"] == "COMPLETED"
    assert repo["commit_count"] == 2


def test_list_repos_has_case_study_flag(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    _insert_case_study(db, repository_id="repo-abc")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos")

    assert response.status_code == 200
    repo = response.json()["repos"][0]
    assert repo["has_case_study"] is True


def test_list_repos_no_case_study_flag_false(client_with_repo: TestClient) -> None:
    response = client_with_repo.get("/api/repos")
    repo = response.json()["repos"][0]
    assert repo["has_case_study"] is False


def test_list_repos_stays_fast_with_many_commits_and_analyses(tmp_path: Path) -> None:
    """Regression test for a JOIN fan-out bug in SqliteRepositoryListReader.

    commit_facts and commit_analyses are both "many" tables keyed on
    repository_id. LEFT JOINing both onto ingestion_runs in one query produces
    their cross product per repository before COUNT(DISTINCT ...) collapses it
    back down — correct counts, but O(commits * analyses) work.

    Measured scaling of the join-based query on this exact schema: n=300 ->
    75ms, n=800 -> 698ms, n=1600 -> 2870ms (quadratic, as expected for a fan-out).
    The scalar-subquery rewrite stays sub-millisecond at every size, including
    on real seeded data (1548 commits / 231 analyses: ~1855ms -> ~0.1ms).
    n=800 here reliably fails against the old query while staying well clear
    of the fixed query's cost.
    """
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    n = 800
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "INSERT INTO commit_facts"
            " (repository_id, sha, committed_at, message, author_name, committer_name, parent_shas)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("repo-abc", f"sha{i:04d}", "2024-01-01T00:00:00", "msg", "a", "a", "[]")
                for i in range(n)
            ],
        )
        conn.executemany(
            "INSERT INTO commit_analyses (repository_id, commit_sha, data) VALUES (?, ?, ?)",
            [("repo-abc", f"sha{i:04d}", "{}") for i in range(n)],
        )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    start = time.perf_counter()
    response = client.get("/api/repos")
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    repo = response.json()["repos"][0]
    assert repo["commit_count"] == n
    assert repo["analysis_count"] == n
    assert elapsed < 0.3, (
        f"GET /api/repos took {elapsed:.2f}s for {n} commits/analyses — "
        "check for a commit_facts x commit_analyses JOIN fan-out regression"
    )


# ---------------------------------------------------------------------------
# GET /api/repos — stars + languages (spec 019)
# ---------------------------------------------------------------------------


def test_list_repos_no_metadata_returns_none_and_empty_languages(
    client_with_repo: TestClient,
) -> None:
    response = client_with_repo.get("/api/repos")
    repo = response.json()["repos"][0]
    assert repo["stars"] is None
    assert repo["languages"] == []


def test_list_repos_includes_stars_and_languages_when_stored(tmp_path: Path) -> None:
    from git_it.api.app import create_app
    from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown, RepoMetadata
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteRepoMetadataStore

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    metadata_store = SqliteRepoMetadataStore(db)
    metadata_store.initialize()
    metadata_store.save_repo_metadata(
        "repo-abc",
        RepoMetadata(
            stars=1234,
            languages=(
                LanguageBreakdown(language="Python", bytes=300),
                LanguageBreakdown(language="HTML", bytes=100),
            ),
        ),
    )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos")

    assert response.status_code == 200
    repo = response.json()["repos"][0]
    assert repo["stars"] == 1234
    assert repo["languages"] == [
        {"language": "Python", "bytes": 300, "percent": 75.0},
        {"language": "HTML", "bytes": 100, "percent": 25.0},
    ]


# ---------------------------------------------------------------------------
# GET /api/repos — default_branch (spec 020)
# ---------------------------------------------------------------------------


def test_list_repos_no_default_branch_returns_none(client_with_repo: TestClient) -> None:
    response = client_with_repo.get("/api/repos")
    repo = response.json()["repos"][0]
    assert repo["default_branch"] is None


def test_list_repos_includes_default_branch_when_stored(tmp_path: Path) -> None:
    from git_it.api.app import create_app
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteDefaultBranchStore

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    branch_store = SqliteDefaultBranchStore(db)
    branch_store.initialize()
    branch_store.save_default_branch("repo-abc", "main")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos")

    assert response.status_code == 200
    repo = response.json()["repos"][0]
    assert repo["default_branch"] == "main"


# ---------------------------------------------------------------------------
# _fetch_and_store_repo_metadata — ingestion-time fetch helper (spec 019)
# ---------------------------------------------------------------------------


def test_fetch_and_store_repo_metadata_skips_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_repo_metadata

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with mock.patch("git_it.api.routes.repos.GithubRepoMetadataFetcher") as mock_fetcher_cls:
        _fetch_and_store_repo_metadata(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )
    mock_fetcher_cls.assert_not_called()


def test_fetch_and_store_repo_metadata_stores_result_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_repo_metadata
    from git_it.repository_ingestion.composition import build_repo_metadata_store
    from git_it.repository_ingestion.domain.repo_metadata import RepoMetadata

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with mock.patch("git_it.api.routes.repos.GithubRepoMetadataFetcher") as mock_fetcher_cls:
        mock_fetcher_cls.return_value.fetch_repo_metadata.return_value = RepoMetadata(
            stars=42, languages=()
        )
        _fetch_and_store_repo_metadata(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )
    store = build_repo_metadata_store(project_root=tmp_path)
    assert store.get_repo_metadata("repo-abc") == RepoMetadata(stars=42, languages=())


def test_fetch_and_store_repo_metadata_noop_when_fetch_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_repo_metadata
    from git_it.repository_ingestion.composition import build_repo_metadata_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with mock.patch("git_it.api.routes.repos.GithubRepoMetadataFetcher") as mock_fetcher_cls:
        mock_fetcher_cls.return_value.fetch_repo_metadata.return_value = None
        _fetch_and_store_repo_metadata(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )
    store = build_repo_metadata_store(project_root=tmp_path)
    assert store.get_repo_metadata("repo-abc") is None


# ---------------------------------------------------------------------------
# _fetch_and_store_discussion_evidence — ingestion-time fetch helper (spec 022)
# ---------------------------------------------------------------------------


def _make_discussion(discussion_id: str = "D_1") -> Any:
    from git_it.repository_ingestion.domain.discussions import Discussion

    return Discussion(
        id=discussion_id,
        url=f"https://github.com/owner/repo/discussions/{discussion_id[-1]}",
        title="Why do we use X?",
        body="Some design question.",
        answer_body="Because of Y.",
        category="Q&A",
        is_answered=True,
        upvote_count=5,
        reaction_count=3,
        comment_count=2,
        updated_at="2024-01-01T00:00:00Z",
    )


def _make_discussion_evidence(discussion_id: str = "D_1") -> Any:
    from datetime import UTC, datetime

    from git_it.repository_ingestion.domain.discussions import DiscussionEvidence

    return DiscussionEvidence(
        discussion_id=discussion_id,
        discussion_url=f"https://github.com/owner/repo/discussions/{discussion_id[-1]}",
        claim_type="design_rationale",
        summary="The team chose X because of Y.",
        confidence=0.8,
        limitations=[],
        source_inputs=[discussion_id],
        generated_at=datetime.now(UTC),
        model="test-model",
    )


def test_fetch_and_store_discussion_evidence_skips_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_discussion_evidence

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with mock.patch("git_it.api.routes.repos.GithubDiscussionsFetcher") as mock_fetcher_cls:
        _fetch_and_store_discussion_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )
    mock_fetcher_cls.assert_not_called()


def test_fetch_and_store_discussion_evidence_stores_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_discussion_evidence
    from git_it.repository_ingestion.composition import build_discussion_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    discussion = _make_discussion()
    evidence = _make_discussion_evidence()

    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = [evidence]

    with (
        mock.patch("git_it.api.routes.repos.GithubDiscussionsFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_discussion_summarizer",
            return_value=stub_summarizer,
        ) as mock_build_summarizer,
    ):
        mock_fetcher_cls.return_value.fetch_qualifying_discussions.return_value = [discussion]
        _fetch_and_store_discussion_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    mock_build_summarizer.assert_called_once()
    stub_summarizer.summarize.assert_called_once_with([discussion])
    store = build_discussion_evidence_store(project_root=tmp_path)
    assert store.get_discussion_evidence("repo-abc") == [evidence]


def test_fetch_and_store_discussion_evidence_noop_when_no_discussions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_discussion_evidence
    from git_it.repository_ingestion.composition import build_discussion_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with (
        mock.patch("git_it.api.routes.repos.GithubDiscussionsFetcher") as mock_fetcher_cls,
        mock.patch("git_it.api.routes.repos.build_discussion_summarizer") as mock_build_summarizer,
    ):
        mock_fetcher_cls.return_value.fetch_qualifying_discussions.return_value = []
        _fetch_and_store_discussion_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    mock_build_summarizer.assert_not_called()
    store = build_discussion_evidence_store(project_root=tmp_path)
    assert store.get_discussion_evidence("repo-abc") == []


def test_fetch_and_store_discussion_evidence_noop_when_summarizer_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_discussion_evidence
    from git_it.repository_ingestion.composition import build_discussion_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    discussion = _make_discussion()
    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = []

    with (
        mock.patch("git_it.api.routes.repos.GithubDiscussionsFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_discussion_summarizer",
            return_value=stub_summarizer,
        ),
    ):
        mock_fetcher_cls.return_value.fetch_qualifying_discussions.return_value = [discussion]
        _fetch_and_store_discussion_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    store = build_discussion_evidence_store(project_root=tmp_path)
    assert store.get_discussion_evidence("repo-abc") == []


def test_fetch_and_store_discussion_evidence_swallows_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_discussion_evidence

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with mock.patch("git_it.api.routes.repos.GithubDiscussionsFetcher") as mock_fetcher_cls:
        mock_fetcher_cls.return_value.fetch_qualifying_discussions.side_effect = RuntimeError(
            "boom"
        )
        # Must not raise: any failure degrades to "no discussion evidence" (spec 022).
        _fetch_and_store_discussion_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )


# ---------------------------------------------------------------------------
# Batch 122 — embedding computation for discussion evidence (spec 023)
# ---------------------------------------------------------------------------


def test_fetch_and_store_discussion_evidence_computes_embeddings_when_openai_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from git_it.api.routes.repos import _fetch_and_store_discussion_evidence
    from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key")
    discussion = _make_discussion()
    evidence = _make_discussion_evidence()

    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = [evidence]

    chunk = EmbeddedChunk(
        repository_id="repo-abc",
        source_type="discussion_evidence",
        source_id=evidence.discussion_url,
        text=evidence.summary,
        vector=[0.1, 0.2],
        model="test-embedding-model",
        created_at=datetime.now(UTC),
    )
    stub_embedding_service = mock.Mock()
    stub_embedding_service.embed_discussion_evidence.return_value = chunk
    stub_embedding_writer = mock.Mock()

    with (
        mock.patch("git_it.api.routes.repos.GithubDiscussionsFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_discussion_summarizer",
            return_value=stub_summarizer,
        ),
        mock.patch(
            "git_it.api.routes.repos.build_embedding_client",
            return_value=mock.Mock(),
        ),
        mock.patch(
            "git_it.api.routes.repos.build_embedding_store",
            return_value=stub_embedding_writer,
        ),
        mock.patch(
            "git_it.api.routes.repos.EmbeddingService",
            return_value=stub_embedding_service,
        ),
    ):
        mock_fetcher_cls.return_value.fetch_qualifying_discussions.return_value = [discussion]
        _fetch_and_store_discussion_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    stub_embedding_service.embed_discussion_evidence.assert_called_once_with("repo-abc", evidence)
    stub_embedding_writer.save_embeddings.assert_called_once_with("repo-abc", [chunk])


def test_fetch_and_store_discussion_evidence_skips_embeddings_when_openai_key_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_discussion_evidence

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    discussion = _make_discussion()
    evidence = _make_discussion_evidence()

    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = [evidence]

    with (
        mock.patch("git_it.api.routes.repos.GithubDiscussionsFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_discussion_summarizer",
            return_value=stub_summarizer,
        ),
        mock.patch(
            "git_it.api.routes.repos.build_embedding_client",
            return_value=None,
        ) as mock_build_embedding_client,
        mock.patch("git_it.api.routes.repos.build_embedding_store") as mock_build_embedding_store,
    ):
        mock_fetcher_cls.return_value.fetch_qualifying_discussions.return_value = [discussion]
        _fetch_and_store_discussion_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    mock_build_embedding_client.assert_called_once()
    mock_build_embedding_store.assert_not_called()


def test_fetch_and_store_discussion_evidence_swallows_embedding_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_discussion_evidence

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key")
    discussion = _make_discussion()
    evidence = _make_discussion_evidence()

    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = [evidence]

    with (
        mock.patch("git_it.api.routes.repos.GithubDiscussionsFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_discussion_summarizer",
            return_value=stub_summarizer,
        ),
        mock.patch(
            "git_it.api.routes.repos.build_embedding_client",
            side_effect=RuntimeError("boom"),
        ),
    ):
        mock_fetcher_cls.return_value.fetch_qualifying_discussions.return_value = [discussion]
        # Must not raise: inherits the existing best-effort try/except (spec 022/023).
        _fetch_and_store_discussion_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )


# ---------------------------------------------------------------------------
# Composition wiring — build_discussion_summarizer / build_narrative_service (spec 022)
# ---------------------------------------------------------------------------


def test_build_discussion_summarizer_returns_discussion_summarizer() -> None:
    from git_it.repository_ingestion.application.discussion_summarizer import (
        DiscussionSummarizer,
    )
    from git_it.repository_ingestion.composition import build_discussion_summarizer

    summarizer = build_discussion_summarizer(model="test-model")
    assert isinstance(summarizer, DiscussionSummarizer)


def test_build_narrative_service_wires_discussion_reader(tmp_path: Path) -> None:
    from git_it.repository_ingestion.composition import build_narrative_service

    svc = build_narrative_service(project_root=tmp_path, model="test-model")
    assert svc._discussion_reader is not None


# ---------------------------------------------------------------------------
# _fetch_and_store_release_evidence / _fetch_and_store_advisory_evidence —
# ingestion-time fetch helpers (spec 026)
# ---------------------------------------------------------------------------


def _make_release(tag_name: str = "v1.0.0") -> Any:
    from git_it.repository_ingestion.domain.releases import Release

    return Release(
        tag_name=tag_name,
        name="Version 1.0.0",
        body="Some release notes.",
        html_url=f"https://github.com/owner/repo/releases/tag/{tag_name}",
        published_at="2024-01-01T00:00:00Z",
        prerelease=False,
    )


def _make_release_evidence(tag_name: str = "v1.0.0") -> Any:
    from datetime import UTC, datetime

    from git_it.repository_ingestion.domain.releases import ReleaseEvidence

    return ReleaseEvidence(
        tag_name=tag_name,
        release_url=f"https://github.com/owner/repo/releases/tag/{tag_name}",
        claim_type="feature_release",
        summary="This release adds a new feature.",
        confidence=0.8,
        limitations=[],
        source_inputs=[tag_name],
        generated_at=datetime.now(UTC),
        model="test-model",
    )


def _make_advisory(ghsa_id: str = "GHSA-xxxx-xxxx-xxxx") -> Any:
    from git_it.repository_ingestion.domain.advisories import SecurityAdvisory

    return SecurityAdvisory(
        ghsa_id=ghsa_id,
        cve_id="CVE-2024-0001",
        summary="A SQL injection vulnerability.",
        description="Detailed description of the vulnerability.",
        severity="high",
        html_url=f"https://github.com/owner/repo/security/advisories/{ghsa_id}",
        published_at="2024-01-01T00:00:00Z",
    )


def _make_advisory_evidence(ghsa_id: str = "GHSA-xxxx-xxxx-xxxx") -> Any:
    from datetime import UTC, datetime

    from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence

    return AdvisoryEvidence(
        ghsa_id=ghsa_id,
        advisory_url=f"https://github.com/owner/repo/security/advisories/{ghsa_id}",
        severity="high",
        summary="A SQL injection vulnerability was fixed.",
        confidence=0.8,
        limitations=[],
        source_inputs=[ghsa_id],
        generated_at=datetime.now(UTC),
        model="test-model",
    )


def test_fetch_and_store_release_evidence_skips_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_release_evidence

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with mock.patch("git_it.api.routes.repos.GithubReleasesFetcher") as mock_fetcher_cls:
        _fetch_and_store_release_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )
    mock_fetcher_cls.assert_not_called()


def test_fetch_and_store_release_evidence_stores_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_release_evidence
    from git_it.repository_ingestion.composition import build_release_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    release = _make_release()
    evidence = _make_release_evidence()

    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = [evidence]

    with (
        mock.patch("git_it.api.routes.repos.GithubReleasesFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_release_summarizer",
            return_value=stub_summarizer,
        ) as mock_build_summarizer,
    ):
        mock_fetcher_cls.return_value.fetch_releases.return_value = [release]
        _fetch_and_store_release_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    mock_build_summarizer.assert_called_once()
    stub_summarizer.summarize.assert_called_once_with([release])
    store = build_release_evidence_store(project_root=tmp_path)
    assert store.get_release_evidence("repo-abc") == [evidence]


def test_fetch_and_store_release_evidence_noop_when_no_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_release_evidence
    from git_it.repository_ingestion.composition import build_release_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with (
        mock.patch("git_it.api.routes.repos.GithubReleasesFetcher") as mock_fetcher_cls,
        mock.patch("git_it.api.routes.repos.build_release_summarizer") as mock_build_summarizer,
    ):
        mock_fetcher_cls.return_value.fetch_releases.return_value = []
        _fetch_and_store_release_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    mock_build_summarizer.assert_not_called()
    store = build_release_evidence_store(project_root=tmp_path)
    assert store.get_release_evidence("repo-abc") == []


def test_fetch_and_store_release_evidence_noop_when_summarizer_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_release_evidence
    from git_it.repository_ingestion.composition import build_release_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    release = _make_release()
    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = []

    with (
        mock.patch("git_it.api.routes.repos.GithubReleasesFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_release_summarizer",
            return_value=stub_summarizer,
        ),
    ):
        mock_fetcher_cls.return_value.fetch_releases.return_value = [release]
        _fetch_and_store_release_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    store = build_release_evidence_store(project_root=tmp_path)
    assert store.get_release_evidence("repo-abc") == []


def test_fetch_and_store_release_evidence_swallows_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_release_evidence

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with mock.patch("git_it.api.routes.repos.GithubReleasesFetcher") as mock_fetcher_cls:
        mock_fetcher_cls.return_value.fetch_releases.side_effect = RuntimeError("boom")
        # Must not raise: any failure degrades to "no release evidence" (spec 026).
        _fetch_and_store_release_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )


def test_fetch_and_store_advisory_evidence_skips_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_advisory_evidence

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with mock.patch("git_it.api.routes.repos.GithubSecurityAdvisoriesFetcher") as mock_fetcher_cls:
        _fetch_and_store_advisory_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )
    mock_fetcher_cls.assert_not_called()


def test_fetch_and_store_advisory_evidence_stores_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_advisory_evidence
    from git_it.repository_ingestion.composition import build_advisory_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    advisory = _make_advisory()
    evidence = _make_advisory_evidence()

    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = [evidence]

    with (
        mock.patch("git_it.api.routes.repos.GithubSecurityAdvisoriesFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_advisory_summarizer",
            return_value=stub_summarizer,
        ) as mock_build_summarizer,
    ):
        mock_fetcher_cls.return_value.fetch_advisories.return_value = [advisory]
        _fetch_and_store_advisory_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    mock_build_summarizer.assert_called_once()
    stub_summarizer.summarize.assert_called_once_with([advisory])
    store = build_advisory_evidence_store(project_root=tmp_path)
    assert store.get_advisory_evidence("repo-abc") == [evidence]


def test_fetch_and_store_advisory_evidence_noop_when_no_advisories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_advisory_evidence
    from git_it.repository_ingestion.composition import build_advisory_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with (
        mock.patch("git_it.api.routes.repos.GithubSecurityAdvisoriesFetcher") as mock_fetcher_cls,
        mock.patch("git_it.api.routes.repos.build_advisory_summarizer") as mock_build_summarizer,
    ):
        mock_fetcher_cls.return_value.fetch_advisories.return_value = []
        _fetch_and_store_advisory_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    mock_build_summarizer.assert_not_called()
    store = build_advisory_evidence_store(project_root=tmp_path)
    assert store.get_advisory_evidence("repo-abc") == []


def test_fetch_and_store_advisory_evidence_noop_when_summarizer_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_advisory_evidence
    from git_it.repository_ingestion.composition import build_advisory_evidence_store

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    advisory = _make_advisory()
    stub_summarizer = mock.Mock()
    stub_summarizer.summarize.return_value = []

    with (
        mock.patch("git_it.api.routes.repos.GithubSecurityAdvisoriesFetcher") as mock_fetcher_cls,
        mock.patch(
            "git_it.api.routes.repos.build_advisory_summarizer",
            return_value=stub_summarizer,
        ),
    ):
        mock_fetcher_cls.return_value.fetch_advisories.return_value = [advisory]
        _fetch_and_store_advisory_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )

    store = build_advisory_evidence_store(project_root=tmp_path)
    assert store.get_advisory_evidence("repo-abc") == []


def test_fetch_and_store_advisory_evidence_swallows_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.routes.repos import _fetch_and_store_advisory_evidence

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    with mock.patch("git_it.api.routes.repos.GithubSecurityAdvisoriesFetcher") as mock_fetcher_cls:
        mock_fetcher_cls.return_value.fetch_advisories.side_effect = RuntimeError("boom")
        # Must not raise: any failure degrades to "no advisory evidence" (spec 026).
        _fetch_and_store_advisory_evidence(
            repository_id="repo-abc",
            canonical_url="https://github.com/owner/repo",
            project_root=tmp_path,
        )


# ---------------------------------------------------------------------------
# Composition wiring — release/advisory factories (spec 026)
# ---------------------------------------------------------------------------


def test_build_release_evidence_store_returns_sqlite_store(tmp_path: Path) -> None:
    from git_it.repository_ingestion.composition import build_release_evidence_store
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteReleaseEvidenceStore

    store = build_release_evidence_store(project_root=tmp_path)
    assert isinstance(store, SqliteReleaseEvidenceStore)
    # initialize() already ran — get_release_evidence must not raise.
    assert store.get_release_evidence("repo-abc") == []


def test_build_advisory_evidence_store_returns_sqlite_store(tmp_path: Path) -> None:
    from git_it.repository_ingestion.composition import build_advisory_evidence_store
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteAdvisoryEvidenceStore

    store = build_advisory_evidence_store(project_root=tmp_path)
    assert isinstance(store, SqliteAdvisoryEvidenceStore)
    assert store.get_advisory_evidence("repo-abc") == []


def test_build_release_summarizer_returns_release_summarizer() -> None:
    from git_it.repository_ingestion.application.release_summarizer import ReleaseSummarizer
    from git_it.repository_ingestion.composition import build_release_summarizer

    summarizer = build_release_summarizer(model="test-model")
    assert isinstance(summarizer, ReleaseSummarizer)


def test_build_advisory_summarizer_returns_advisory_summarizer() -> None:
    from git_it.repository_ingestion.application.advisory_summarizer import AdvisorySummarizer
    from git_it.repository_ingestion.composition import build_advisory_summarizer

    summarizer = build_advisory_summarizer(model="test-model")
    assert isinstance(summarizer, AdvisorySummarizer)


# ---------------------------------------------------------------------------
# GET /api/repos/{id}/case-study
# ---------------------------------------------------------------------------


def test_get_case_study_404_when_missing(client_with_repo: TestClient) -> None:
    response = client_with_repo.get("/api/repos/repo-abc/case-study")
    assert response.status_code == 404


def test_get_case_study_returns_narrative(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_case_study(
        db,
        repository_id="repo-xyz",
        narrative="# Engineering Case Study\n\nThis repo is fascinating.",
        commit_count=10,
        hotspot_count=3,
    )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-xyz/case-study")

    assert response.status_code == 200
    body = response.json()
    assert body["repository_id"] == "repo-xyz"
    assert "fascinating" in body["narrative"]
    assert body["commit_count"] == 10
    assert body["hotspot_count"] == 3


# ---------------------------------------------------------------------------
# GET /api/repos/{id}/commits
# ---------------------------------------------------------------------------


def test_get_commits_returns_paginated(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    for i in range(10):
        _insert_commit(
            db,
            repository_id="repo-abc",
            sha=f"sha{i:04d}",
            committed_at=f"2024-01-{i + 1:02d}T10:00:00",
            message=f"commit {i}",
        )
        _insert_analysis(db, commit_sha=f"sha{i:04d}", category="feature", summary=f"commit {i}")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/commits?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert len(body["commits"]) == 5  # page respects limit
    assert body["total"] == 10  # total reflects full DB count, not page size
    assert body["repository_id"] == "repo-abc"


def test_get_commits_order_newest_first(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    _insert_commit(db, sha="old111", committed_at="2023-01-01T10:00:00", message="old commit")
    _insert_commit(db, sha="new222", committed_at="2024-06-01T10:00:00", message="new commit")
    _insert_analysis(db, commit_sha="old111", category="chore", summary="old")
    _insert_analysis(db, commit_sha="new222", category="feature", summary="new")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/commits?order=newest")

    commits = response.json()["commits"]
    assert commits[0]["sha"] == "new222"
    assert commits[1]["sha"] == "old111"


def test_get_commits_order_oldest_first(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    _insert_commit(db, sha="old111", committed_at="2023-01-01T10:00:00", message="old commit")
    _insert_commit(db, sha="new222", committed_at="2024-06-01T10:00:00", message="new commit")
    _insert_analysis(db, commit_sha="old111", category="chore", summary="old")
    _insert_analysis(db, commit_sha="new222", category="feature", summary="new")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/commits?order=oldest")

    commits = response.json()["commits"]
    assert commits[0]["sha"] == "old111"
    assert commits[1]["sha"] == "new222"


def test_get_commits_includes_analysis_data(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    _insert_commit(db, sha="aaa111", message="fix: bug fix")
    _insert_analysis(db, commit_sha="aaa111", category="bugfix", summary="Fixed null pointer")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/commits")

    assert response.status_code == 200
    commit = response.json()["commits"][0]
    assert commit["sha"] == "aaa111"
    assert commit["category"] == "bugfix"
    assert commit["summary"] == "Fixed null pointer"


def test_get_commits_404_for_unknown_repo_on_populated_db(client_empty: TestClient) -> None:
    """Spec 008 AC: an unknown repository_id must 404, even when the database
    itself is provisioned (other repositories may already exist in it)."""
    response = client_empty.get("/api/repos/repo-does-not-exist/commits")
    assert response.status_code == 404


def test_get_commits_returns_200_empty_for_known_repo_with_no_data(
    client_with_repo: TestClient,
) -> None:
    """A known repository (has an ingestion run) with no commits yet must stay
    200-empty — the 404 guard is only for unknown repositories."""
    response = client_with_repo.get("/api/repos/repo-abc/commits")
    assert response.status_code == 200
    body = response.json()
    assert body["commits"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/repos/{id}/patterns
# ---------------------------------------------------------------------------


def test_get_patterns_returns_report(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/patterns")

    assert response.status_code == 200
    body = response.json()
    assert body["repository_id"] == "repo-abc"
    assert "hotspots" in body
    assert isinstance(body["hotspots"], list)


def test_get_patterns_returns_hotspot_when_file_exceeds_threshold(tmp_path: Path) -> None:
    """Pattern detection returns a hotspot with correct fields when file_facts are seeded."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")

    # Insert 10 commits each touching the same file to ensure it exceeds the default threshold (5)
    for i in range(10):
        sha = f"sha{i:04d}"
        _insert_commit(
            db, repository_id="repo-abc", sha=sha, committed_at=f"2024-01-{i + 1:02d}T10:00:00"
        )
        _insert_file_fact(
            db,
            repository_id="repo-abc",
            commit_sha=sha,
            file_path="src/hotfile.py",
            insertions=5,
            deletions=3,
        )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/patterns?hotspot_threshold=5")

    assert response.status_code == 200
    body = response.json()
    assert body["repository_id"] == "repo-abc"
    hotspots = body["hotspots"]
    assert len(hotspots) >= 1
    top = hotspots[0]
    assert top["file_path"] == "src/hotfile.py"
    assert top["commit_count"] == 10
    assert top["churn"] == 80  # 10 commits × (5 insertions + 3 deletions)


def test_get_patterns_404_for_unknown_repo_on_populated_db(client_empty: TestClient) -> None:
    """Spec 008 AC: an unknown repository_id must 404, even when the database
    itself is provisioned (other repositories may already exist in it)."""
    response = client_empty.get("/api/repos/repo-does-not-exist/patterns")
    assert response.status_code == 404


def test_get_patterns_returns_200_empty_for_known_repo_with_no_data(
    client_with_repo: TestClient,
) -> None:
    """A known repository (has an ingestion run) with no commit data yet must
    stay 200-empty — the 404 guard is only for unknown repositories."""
    response = client_with_repo.get("/api/repos/repo-abc/patterns")
    assert response.status_code == 200
    body = response.json()
    assert body["hotspots"] == []
