"""AC-2: GET /case-study response includes available_audiences — spec 010."""

import sqlite3
from pathlib import Path


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


def _seed_case_study(db: Path, repository_id: str, audience: str) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO case_studies
              (repository_id, narrative, commit_count, hotspot_count, audience)
            VALUES (?, ?, ?, ?, ?)
            """,
            (repository_id, "## Overview\nTest narrative.", 5, 1, audience),
        )


def test_case_study_response_includes_available_audiences_single(
    tmp_path: Path,
) -> None:
    """AC-2: response lists the one audience that has been generated."""
    from fastapi.testclient import TestClient

    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _seed_case_study(db, "repo-test", "beginner")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/repos/repo-test/case-study?audience=beginner")
    assert resp.status_code == 200
    body = resp.json()
    assert "available_audiences" in body, "field missing from response"
    assert body["available_audiences"] == ["beginner"]


def test_case_study_response_available_audiences_excludes_missing(
    tmp_path: Path,
) -> None:
    """AC-2: only the seeded audience appears; the other is absent."""
    from fastapi.testclient import TestClient

    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _seed_case_study(db, "repo-test", "beginner")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/repos/repo-test/case-study?audience=beginner")
    assert resp.status_code == 200
    available = resp.json()["available_audiences"]
    assert "expert" not in available, f"expert should not be listed; got {available}"


def test_case_study_response_available_audiences_both_when_both_generated(
    tmp_path: Path,
) -> None:
    """AC-2: both audiences appear when both rows exist."""
    from fastapi.testclient import TestClient

    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _seed_case_study(db, "repo-test", "beginner")
    _seed_case_study(db, "repo-test", "expert")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/repos/repo-test/case-study?audience=beginner")
    assert resp.status_code == 200
    available = resp.json()["available_audiences"]
    assert sorted(available) == ["beginner", "expert"]
