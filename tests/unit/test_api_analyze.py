"""Tests for analyze and ingest API routes.

Covers:
- GET /api/repos/{repository_id}/analyze/estimate
- POST /api/repos/{repository_id}/analyze
- GET /api/repos/{repository_id}/analyze/status
- POST /api/repos/ingest

All tests use FastAPI's TestClient with a temporary SQLite DB.
No network, no external services, fully deterministic.
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import cast

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
    """Create all tables needed by the analyze/ingest endpoints."""
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
                author_email TEXT NOT NULL DEFAULT '',
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
        conn.commit()


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
            " (repository_id, sha, committed_at, message, author_name, committer_name,"
            "  parent_shas, author_email)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (repository_id, sha, committed_at, message, author_name, author_name, "[]", ""),
        )


def _insert_analysis(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    commit_sha: str = "aaa111",
    category: str = "feature",
) -> None:
    # JSON must be valid CommitAnalysis — category lowercase, confidence required
    data = json.dumps(
        {
            "commit_sha": commit_sha,
            "category": category.lower(),
            "summary": "test summary",
            "risk_level": "low",
            "confidence": 0.9,
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


def _canonical_repo_id(canonical_url: str) -> str:
    return "repo-" + hashlib.sha256(canonical_url.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/analyze/estimate
# ---------------------------------------------------------------------------


def test_estimate_returns_404_when_db_missing(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/analyze/estimate")
    assert response.status_code == 404


def test_estimate_404_for_unknown_repo_on_populated_db(tmp_path: Path) -> None:
    """Spec 008 AC: an unknown repository_id must 404 even when the database
    is provisioned and already holds data for other repositories."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-known")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-does-not-exist/analyze/estimate")
    assert response.status_code == 404


def test_estimate_returns_correct_counts(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    for i in range(5):
        _insert_commit(db, sha=f"sha{i:04d}", committed_at=f"2024-01-{i + 1:02d}T10:00:00")
    # Analyze only 2 of the 5
    _insert_analysis(db, commit_sha="sha0000")
    _insert_analysis(db, commit_sha="sha0001")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/analyze/estimate")

    assert response.status_code == 200
    body = response.json()
    assert body["total_commits"] == 5
    assert body["analyzed_commits"] == 2
    assert body["unanalyzed_commits"] == 3


def test_estimate_cost_proportional_to_llm_calls(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    # Insert commits with messages that the pre-classifier won't skip
    for i in range(3):
        _insert_commit(
            db,
            sha=f"sha{i:04d}",
            committed_at=f"2024-01-{i + 1:02d}T10:00:00",
            message=f"feat: feature {i}",
        )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/analyze/estimate")

    assert response.status_code == 200
    body = response.json()
    llm_calls = body["estimated_llm_calls"]
    assert body["estimated_analysis_cost_usd"] == round(llm_calls * 0.0008, 4)
    assert body["estimated_narrative_cost_usd"] > 0
    assert body["estimated_cost_usd"] == round(
        body["estimated_analysis_cost_usd"] + body["estimated_narrative_cost_usd"], 4
    )


def test_estimate_narrative_cost_scales_with_commits(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db_small = _db_path(tmp_path / "small")
    db_large = _db_path(tmp_path / "large")
    _init_db(db_small)
    _init_db(db_large)
    _insert_ingestion_run(db_small)
    _insert_ingestion_run(db_large)
    _insert_commit(db_small, sha="sha0000", message="feat: a")
    for i in range(20):
        _insert_commit(db_large, sha=f"sha{i:04d}", message=f"feat: {i}")

    client_small = TestClient(create_app(project_root=tmp_path / "small"))
    client_large = TestClient(create_app(project_root=tmp_path / "large"))

    small_cost = client_small.get("/api/repos/repo-abc/analyze/estimate").json()[
        "estimated_narrative_cost_usd"
    ]
    large_cost = client_large.get("/api/repos/repo-abc/analyze/estimate").json()[
        "estimated_narrative_cost_usd"
    ]
    assert large_cost > small_cost


def test_estimate_narrative_cost_zero_when_no_commits(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    client = TestClient(create_app(project_root=tmp_path))
    body = client.get("/api/repos/repo-abc/analyze/estimate").json()
    assert body["estimated_narrative_cost_usd"] == 0.0


def test_estimate_zero_calls_when_all_analyzed(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    _insert_commit(db, sha="sha0000")
    _insert_analysis(db, commit_sha="sha0000")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/analyze/estimate")

    assert response.status_code == 200
    body = response.json()
    assert body["estimated_llm_calls"] == 0


# ---------------------------------------------------------------------------
# POST /api/repos/{repository_id}/analyze
# ---------------------------------------------------------------------------


def test_analyze_returns_404_when_db_missing(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/analyze", json={})
    assert response.status_code == 404


def test_analyze_returns_analyzing_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    # POSTing to /analyze spawns a real background thread that runs
    # `_analyze_bg`, which mutates the module-level `_analyze_progress` dict
    # (setting running=True). Nothing in that flow ever resets it, so a
    # leaked entry can bleed into other tests (e.g. the delete-repo suite)
    # that share the default "repo-abc" id. This test only cares about the
    # endpoint's immediate response, so replace the background worker with
    # a no-op — the thread still spawns (matching production wiring) but
    # never touches shared state.
    monkeypatch.setattr(repos_module, "_analyze_bg", lambda *args, **kwargs: None)

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="aaa111")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/analyze", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ANALYZING"


def test_analyze_accepts_any_litellm_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    # Same background-thread leak concern as above — no-op the worker.
    monkeypatch.setattr(repos_module, "_analyze_bg", lambda *args, **kwargs: None)

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="aaa111")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/repos/repo-abc/analyze",
        json={"model": "openai/gpt-4o"},
    )
    assert response.status_code == 200


def test_analyze_requires_auth_when_api_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")
    db = _db_path(tmp_path)
    _init_db(db)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/analyze", json={})
    assert response.status_code == 401


def test_analyze_accepts_valid_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    # Same background-thread leak concern as the tests above — no-op the worker.
    monkeypatch.setattr(repos_module, "_analyze_bg", lambda *args, **kwargs: None)

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="aaa111")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/repos/repo-abc/analyze",
        json={},
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code != 401


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/analyze/status
# ---------------------------------------------------------------------------


def test_analyze_status_defaults_when_no_analysis_running(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-test123/analyze/status")

    assert response.status_code == 200
    body = response.json()
    assert body["running"] is False
    assert body["done"] == 0
    assert body["total"] == 0
    assert body["pct"] == 0


def test_analyze_status_returns_live_progress(tmp_path: Path) -> None:
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _analyze_progress

    repo_id = "repo-test123-live"
    _analyze_progress[repo_id] = {"running": True, "done": 5, "total": 20}
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)
        response = client.get(f"/api/repos/{repo_id}/analyze/status")

        assert response.status_code == 200
        body = response.json()
        assert body["running"] is True
        assert body["done"] == 5
        assert body["total"] == 20
        assert body["pct"] == 25
    finally:
        _analyze_progress.pop(repo_id, None)


def test_analyze_status_pct_zero_when_total_zero(tmp_path: Path) -> None:
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _analyze_progress

    repo_id = "repo-pct-zero"
    _analyze_progress[repo_id] = {"running": True, "done": 0, "total": 0}
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)
        response = client.get(f"/api/repos/{repo_id}/analyze/status")

        assert response.status_code == 200
        assert response.json()["pct"] == 0
    finally:
        _analyze_progress.pop(repo_id, None)


def test_analyze_status_pct_100_when_complete(tmp_path: Path) -> None:
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _analyze_progress

    repo_id = "repo-pct-100"
    _analyze_progress[repo_id] = {"running": False, "done": 10, "total": 10}
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)
        response = client.get(f"/api/repos/{repo_id}/analyze/status")

        assert response.status_code == 200
        assert response.json()["pct"] == 100
    finally:
        _analyze_progress.pop(repo_id, None)


def test_cancel_analyze_marks_cancel_requested_for_running_analysis(tmp_path: Path) -> None:
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _analyze_progress

    repo_id = "repo-cancel-running"
    _analyze_progress[repo_id] = {
        "running": True,
        "done": 1,
        "total": 3,
        "cancel_requested": False,
        "cancelled": False,
    }
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)
        response = client.post(f"/api/repos/{repo_id}/analyze/cancel")

        assert response.status_code == 200
        body = response.json()
        assert body["running"] is True
        assert body["cancel_requested"] is True
        assert body["cancelled"] is False
    finally:
        _analyze_progress.pop(repo_id, None)


def test_cancel_analyze_requires_auth_when_api_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/analyze/cancel")
    assert response.status_code == 401


def test_analyze_status_exposes_cancel_flags(tmp_path: Path) -> None:
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _analyze_progress

    repo_id = "repo-cancel-status"
    _analyze_progress[repo_id] = {
        "running": False,
        "done": 1,
        "total": 3,
        "cancel_requested": True,
        "cancelled": True,
    }
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)
        response = client.get(f"/api/repos/{repo_id}/analyze/status")

        assert response.status_code == 200
        body = response.json()
        assert body["cancel_requested"] is True
        assert body["cancelled"] is True
    finally:
        _analyze_progress.pop(repo_id, None)


def test_analyze_bg_skips_case_study_when_cancel_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import git_it.api.routes.repos as repos_module

    narrative_calls = 0

    class _FakeAnalysisService:
        def analyze_commits(self, *args: object, **kwargs: object) -> None:
            should_cancel = cast(Callable[[], bool], kwargs["should_cancel"])
            with repos_module._analyze_progress_lock:
                repos_module._analyze_progress["repo-abc"]["cancel_requested"] = True
            assert should_cancel() is True

    class _FakeNarrativeService:
        def generate(self, *args: object, **kwargs: object) -> None:
            nonlocal narrative_calls
            narrative_calls += 1

    monkeypatch.setattr(
        repos_module, "build_commit_analysis_service", lambda **kwargs: _FakeAnalysisService()
    )
    monkeypatch.setattr(
        repos_module, "build_narrative_service", lambda **kwargs: _FakeNarrativeService()
    )

    repos_module._analyze_bg("repo-abc", 10, "gpt-4o-mini", tmp_path)

    assert narrative_calls == 0
    assert repos_module._analyze_progress["repo-abc"]["running"] is False
    assert repos_module._analyze_progress["repo-abc"]["cancelled"] is True
    repos_module._analyze_progress.pop("repo-abc", None)


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/analyze/status -- fail-loud (spec 021)
# ---------------------------------------------------------------------------


def test_analyze_status_error_is_none_by_default(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-test123/analyze/status")

    assert response.status_code == 200
    assert response.json()["error"] is None


def test_analyze_status_error_is_none_when_progress_has_no_error_key(tmp_path: Path) -> None:
    """Backward compatibility: entries seeded without an 'error' key (as several
    pre-existing tests in this file do) must not crash and must report error: None."""
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _analyze_progress

    repo_id = "repo-legacy-progress"
    _analyze_progress[repo_id] = {"running": False, "done": 10, "total": 10}
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)
        response = client.get(f"/api/repos/{repo_id}/analyze/status")

        assert response.status_code == 200
        assert response.json()["error"] is None
    finally:
        _analyze_progress.pop(repo_id, None)


def test_analyze_bg_failure_surfaces_sanitized_error_type_in_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 021: a background analysis failure must be visible via the status
    endpoint as running=False + error=<ExceptionTypeName>, instead of being
    silently swallowed."""
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    class _BoomAnalysisError(Exception):
        pass

    def _raise(*args: object, **kwargs: object) -> None:
        raise _BoomAnalysisError("connection string: postgres://user:sk-SECRET123@host/db")

    monkeypatch.setattr(repos_module, "build_commit_analysis_service", _raise)

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="aaa111")

    # Call the background worker synchronously -- no real thread needed here.
    repos_module._analyze_bg("repo-abc", 10, "gpt-4o-mini", tmp_path)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/analyze/status")

    assert response.status_code == 200
    body = response.json()
    assert body["running"] is False
    assert body["error"] == "_BoomAnalysisError"


def test_analyze_bg_failure_never_leaks_raw_exception_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Security regression (CODEX): the raw exception message may carry provider
    API keys, connection strings, or file paths -- only the sanitized type name
    may ever reach the API response."""
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    secret = "sk-SECRET123"

    def _raise(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"leaked provider key: {secret}")

    monkeypatch.setattr(repos_module, "build_commit_analysis_service", _raise)

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="aaa111")

    repos_module._analyze_bg("repo-abc", 10, "gpt-4o-mini", tmp_path)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/analyze/status")

    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["error"] == "RuntimeError"


def test_analyze_bg_success_leaves_error_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Success path must not set an error, even after a prior failure occupied
    the same progress-dict slot."""
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="aaa111")

    class _FakeAnalysisService:
        def analyze_commits(self, *args: object, **kwargs: object) -> None:
            return None

    class _FakeNarrativeService:
        def generate(self, *args: object, **kwargs: object) -> None:
            return None

    monkeypatch.setattr(
        repos_module, "build_commit_analysis_service", lambda **kwargs: _FakeAnalysisService()
    )
    monkeypatch.setattr(
        repos_module, "build_narrative_service", lambda **kwargs: _FakeNarrativeService()
    )

    repos_module._analyze_bg("repo-abc", 10, "gpt-4o-mini", tmp_path)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/analyze/status")

    assert response.status_code == 200
    assert response.json()["error"] is None


# ---------------------------------------------------------------------------
# POST /api/repos/ingest
# ---------------------------------------------------------------------------


def test_ingest_returns_ingesting_status(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/repos/ingest",
        json={"url": "https://github.com/owner/repo"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "INGESTING"
    assert body["canonical_url"] == "https://github.com/owner/repo"


def test_ingest_normalizes_shorthand_url(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/repos/ingest",
        json={"url": "owner/repo"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["canonical_url"] == "https://github.com/owner/repo"


def test_ingest_rejects_invalid_url(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    # HTTP instead of HTTPS — unsupported
    response = client.post(
        "/api/repos/ingest",
        json={"url": "http://github.com/owner/repo"},
    )
    assert response.status_code == 422


def test_ingest_repository_id_is_deterministic(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    r1 = client.post("/api/repos/ingest", json={"url": "https://github.com/owner/repo"})
    r2 = client.post("/api/repos/ingest", json={"url": "https://github.com/owner/repo"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["repository_id"] == r2.json()["repository_id"]


def test_ingest_requires_auth_when_api_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/repos/ingest",
        json={"url": "https://github.com/owner/repo"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting — GET /api/repos/{repository_id}/analyze/estimate
# ---------------------------------------------------------------------------


def test_estimate_analyze_is_rate_limited_at_20_per_minute() -> None:
    """estimate_analyze must carry @limiter.limit('20/minute') for cost control.

    Strategy: introspection of slowapi's limiter registry.  ``@limiter.limit()``
    records each decorated endpoint in ``limiter._route_limits`` keyed by the
    function's fully-qualified name; the value is a list of ``Limit`` objects.
    We assert the estimate endpoint is registered with a 20/minute limit.  This
    is deterministic and isolated — it does not hammer the shared in-memory
    limiter bucket (which would interfere with the other estimate tests).
    """
    import git_it.api.routes.repos  # noqa: F401 — ensure decorators are registered
    from git_it.api.limiter import limiter

    key = "git_it.api.routes.repos.estimate_analyze"
    assert key in limiter._route_limits, (
        "estimate_analyze must be decorated with @limiter.limit — it is not registered "
        "in limiter._route_limits. Add @limiter.limit('20/minute') above the function."
    )
    limit_strs = [str(lim.limit) for lim in limiter._route_limits[key]]
    assert any("20 per 1 minute" in s for s in limit_strs), (
        f"estimate_analyze must be rate-limited at 20/minute; found limits: {limit_strs}"
    )
