"""Tests for the embedding backfill status/run API routes (spec 027, batch 147).

Covers:
- GET /api/repos/{repository_id}/backfill-embeddings (status/availability)
- POST /api/repos/{repository_id}/backfill-embeddings (run)

All tests use FastAPI's TestClient with a temporary SQLite DB and a fake
``EmbeddingBackfillService`` injected via monkeypatch on
``build_embedding_backfill_service`` -- no real network/LLM calls, mirroring
test_api_analyze.py's ``build_commit_analysis_service`` injection pattern.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from git_it.repository_ingestion.application.embedding_backfill_service import (
    EmbeddingBackfillResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_path(tmp_path: Path) -> Path:
    data_dir = tmp_path / ".data" / "git-it" / "ingestion"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "git-it.sqlite3"


def _init_db(db: Path) -> None:
    """Create the ingestion_runs table -- the only table the repo-existence gate reads."""
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
        conn.commit()


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
        conn.commit()


class _FakeBackfillService:
    """Test double for EmbeddingBackfillService -- no real embedder, no network."""

    def __init__(
        self,
        *,
        available: bool,
        missing: int = 0,
        result: EmbeddingBackfillResult | None = None,
    ) -> None:
        self.is_available = available
        self._missing = missing
        self._result = result or EmbeddingBackfillResult(embedded=0, already_present=0, failed=0)

    def estimate_backfill_calls(self, repository_id: str) -> int:
        return self._missing

    def backfill(self, repository_id: str) -> EmbeddingBackfillResult:
        return self._result


def _patch_service(monkeypatch: pytest.MonkeyPatch, service: _FakeBackfillService) -> None:
    import git_it.api.routes.repos as repos_module

    monkeypatch.setattr(
        repos_module,
        "build_embedding_backfill_service",
        lambda **kwargs: service,
    )


# ---------------------------------------------------------------------------
# GET /api/repos/{repository_id}/backfill-embeddings (status)
# ---------------------------------------------------------------------------


def test_status_returns_404_when_db_missing(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/backfill-embeddings")
    assert response.status_code == 404


def test_status_returns_404_for_unknown_repository(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-known")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-does-not-exist/backfill-embeddings")
    assert response.status_code == 404


def test_status_available_false_and_missing_zero_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    _patch_service(monkeypatch, _FakeBackfillService(available=False, missing=0))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/backfill-embeddings")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["missing"] == 0


def test_status_available_true_reports_missing_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    _patch_service(monkeypatch, _FakeBackfillService(available=True, missing=7))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/backfill-embeddings")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["missing"] == 7


# ---------------------------------------------------------------------------
# POST /api/repos/{repository_id}/backfill-embeddings (run)
# ---------------------------------------------------------------------------


def test_run_returns_404_when_db_missing(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/backfill-embeddings")
    assert response.status_code == 404


def test_run_returns_404_for_unknown_repository(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-known")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-does-not-exist/backfill-embeddings")
    assert response.status_code == 404


def test_run_performs_backfill_and_returns_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    fake_result = EmbeddingBackfillResult(embedded=6, already_present=2, failed=1)
    _patch_service(monkeypatch, _FakeBackfillService(available=True, result=fake_result))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/backfill-embeddings")

    assert response.status_code == 200
    body = response.json()
    assert body["embedded"] == 6
    assert body["already_present"] == 2
    assert body["failed"] == 1


def test_run_returns_honest_unavailable_response_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec 027: no OPENAI_API_KEY must never yield a silent/fake success (AC 5)."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    _patch_service(monkeypatch, _FakeBackfillService(available=False))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/backfill-embeddings")

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_run_requires_auth_when_api_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from git_it.api.app import create_app

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/backfill-embeddings")
    assert response.status_code == 401


def test_run_accepts_valid_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from git_it.api.app import create_app

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    _patch_service(monkeypatch, _FakeBackfillService(available=True))

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/repos/repo-abc/backfill-embeddings",
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code != 401
