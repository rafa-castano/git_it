"""Tests for the Git It REST API — Batch 47.

All tests use FastAPI's TestClient with a temporary SQLite DB.
No network, no external services, fully deterministic.
"""

import json
import sqlite3
from pathlib import Path

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
    assert len(body["commits"]) == 5
    assert body["total"] == 5
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
