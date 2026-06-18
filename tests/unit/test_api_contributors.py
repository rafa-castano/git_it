"""Tests for GET /api/repos/{repository_id}/contributors.

All tests use FastAPI's TestClient with a temporary SQLite DB.
No network, no external services, fully deterministic.
"""

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_path(tmp_path: Path) -> Path:
    data_dir = tmp_path / ".data" / "git-it" / "ingestion"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "git-it.sqlite3"


def _init_db(db: Path) -> None:
    """Create all tables needed by the contributors endpoint."""
    with sqlite3.connect(db) as conn:
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
        conn.commit()


def _insert_commit(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    sha: str = "aaa111",
    committed_at: str = "2024-01-01T10:00:00",
    message: str = "feat: first commit",
    author_name: str = "Alice",
    author_email: str = "",
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO commit_facts"
            " (repository_id, sha, committed_at, message, author_name, committer_name,"
            "  parent_shas, author_email)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                repository_id,
                sha,
                committed_at,
                message,
                author_name,
                author_name,
                "[]",
                author_email,
            ),
        )


def _insert_analysis(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    commit_sha: str = "aaa111",
    category: str = "FEATURE",
) -> None:
    import json

    data = json.dumps({"commit_sha": commit_sha, "category": category, "summary": "test"})
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO commit_analyses (repository_id, commit_sha, data)"
            " VALUES (?, ?, ?)",
            (repository_id, commit_sha, data),
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_contributors_returns_404_when_db_missing(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")
    assert response.status_code == 404


def test_contributors_returns_404_when_no_commits(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    # DB exists but commit_facts is empty for this repo
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")
    assert response.status_code == 404


def test_contributors_returns_commit_count_per_author(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="a001", author_name="Alice")
    _insert_commit(db, sha="a002", author_name="Alice", committed_at="2024-01-02T10:00:00")
    _insert_commit(db, sha="a003", author_name="Alice", committed_at="2024-01-03T10:00:00")
    _insert_commit(db, sha="b001", author_name="Bob", committed_at="2024-01-04T10:00:00")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    # Sorted by commit_count DESC — Alice first
    top = body["contributors"][0]
    assert top["author_name"] == "Alice"
    assert top["commit_count"] == 3


def test_contributors_is_bot_true_for_bot_suffix(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="d001", author_name="dependabot[bot]")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    contributor = response.json()["contributors"][0]
    assert contributor["is_bot"] is True


def test_contributors_is_bot_false_for_human(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="h001", author_name="Alice Smith")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    contributor = response.json()["contributors"][0]
    assert contributor["is_bot"] is False


def test_contributors_github_username_from_new_noreply_email(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(
        db,
        sha="g001",
        author_name="Alice",
        author_email="12345678+alice@users.noreply.github.com",
    )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    contributor = response.json()["contributors"][0]
    assert contributor["github_username"] == "alice"


def test_contributors_github_username_from_old_noreply_email(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(
        db,
        sha="g002",
        author_name="Alice",
        author_email="alice@users.noreply.github.com",
    )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    contributor = response.json()["contributors"][0]
    assert contributor["github_username"] == "alice"


def test_contributors_github_username_none_for_regular_email(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(
        db,
        sha="g003",
        author_name="Alice",
        author_email="alice@example.com",
    )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    contributor = response.json()["contributors"][0]
    assert contributor["github_username"] is None


def test_contributors_category_counts_from_analyses(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="c001", author_name="Alice")
    _insert_analysis(db, commit_sha="c001", category="BUGFIX")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    contributor = response.json()["contributors"][0]
    assert contributor["category_counts"].get("BUGFIX") == 1


def test_contributors_active_days_counts_distinct_days(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    # 3 commits on day 1
    _insert_commit(db, sha="d001", author_name="Alice", committed_at="2024-01-01T09:00:00")
    _insert_commit(db, sha="d002", author_name="Alice", committed_at="2024-01-01T12:00:00")
    _insert_commit(db, sha="d003", author_name="Alice", committed_at="2024-01-01T17:00:00")
    # 2 commits on day 2
    _insert_commit(db, sha="d004", author_name="Alice", committed_at="2024-01-02T10:00:00")
    _insert_commit(db, sha="d005", author_name="Alice", committed_at="2024-01-02T15:00:00")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    contributor = response.json()["contributors"][0]
    assert contributor["active_days"] == 2


def test_contributors_migration_guard_survives_existing_column(tmp_path: Path) -> None:
    """Endpoint must not 500 when author_email column already exists in DB."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)  # already creates author_email column
    _insert_commit(db, sha="m001", author_name="Alice", author_email="alice@example.com")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/api/repos/repo-abc/contributors")

    assert response.status_code == 200
    assert response.json()["total"] == 1
