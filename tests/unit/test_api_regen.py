"""Tests for the case-study regenerate / regen-status API routes (spec 021: fail-loud).

Covers:
- GET /api/repos/{repository_id}/case-study/regen-status default/error surfacing
- `_regen_bg` failure sanitization -- the raw exception message must never leak

All tests use FastAPI's TestClient with a temporary SQLite DB. The background worker
is called directly (never a real thread) with a mocked dependency, matching the
pattern used for `_analyze_bg` in test_api_analyze.py.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _db_path(tmp_path: Path) -> Path:
    data_dir = tmp_path / ".data" / "git-it" / "ingestion"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "git-it.sqlite3"


def _init_db(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        conn.executescript(
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
            );
            CREATE TABLE IF NOT EXISTS case_studies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id TEXT NOT NULL,
                narrative TEXT NOT NULL,
                commit_count INTEGER NOT NULL DEFAULT 0,
                hotspot_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                audience TEXT NOT NULL DEFAULT 'beginner',
                UNIQUE(repository_id, audience)
            );
            """
        )


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/case-study/regen-status
# ---------------------------------------------------------------------------


def test_regen_status_defaults_when_no_regen_running(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-test123/case-study/regen-status")

    assert response.status_code == 200
    body = response.json()
    assert body["running"] is False
    assert body["error"] is None


def test_regen_status_error_none_when_progress_has_no_error_key(tmp_path: Path) -> None:
    """Backward compatibility: an entry seeded without an 'error' key must not
    crash and must report error: None."""
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _regen_progress

    repo_id = "repo-legacy-regen"
    _regen_progress[repo_id] = {"running": False, "audience": "beginner"}
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)
        response = client.get(f"/api/repos/{repo_id}/case-study/regen-status")

        assert response.status_code == 200
        assert response.json()["error"] is None
    finally:
        _regen_progress.pop(repo_id, None)


def test_regen_bg_failure_surfaces_sanitized_error_type_in_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 021: a background regen failure must be visible via the status
    endpoint as running=False + error=<ExceptionTypeName>, instead of being
    silently swallowed."""
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    class _BoomRegenError(Exception):
        pass

    def _raise(*args: object, **kwargs: object) -> None:
        raise _BoomRegenError("provider key sk-SECRET123 leaked here")

    monkeypatch.setattr(repos_module, "build_narrative_service", _raise)

    db = _db_path(tmp_path)
    _init_db(db)

    repos_module._regen_bg("repo-abc", "beginner", "gpt-4o-mini", tmp_path)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/case-study/regen-status")

    assert response.status_code == 200
    body = response.json()
    assert body["running"] is False
    assert body["error"] == "_BoomRegenError"


def test_regen_bg_failure_never_leaks_raw_exception_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Security regression (CODEX): raw exception content must never reach the API."""
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    secret = "sk-SECRET123"

    def _raise(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"leaked provider key: {secret}")

    monkeypatch.setattr(repos_module, "build_narrative_service", _raise)

    db = _db_path(tmp_path)
    _init_db(db)

    repos_module._regen_bg("repo-abc", "beginner", "gpt-4o-mini", tmp_path)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/case-study/regen-status")

    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["error"] == "RuntimeError"


def test_regen_bg_success_leaves_error_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import git_it.api.routes.repos as repos_module
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)

    class _FakeNarrativeService:
        def generate(self, *args: object, **kwargs: object) -> None:
            return None

    monkeypatch.setattr(
        repos_module, "build_narrative_service", lambda **kwargs: _FakeNarrativeService()
    )

    repos_module._regen_bg("repo-abc", "beginner", "gpt-4o-mini", tmp_path)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/case-study/regen-status")

    assert response.status_code == 200
    assert response.json()["error"] is None
