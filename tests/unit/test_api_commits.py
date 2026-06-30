"""Tests for GET /api/repos/{repository_id}/commits — Batch 80.

Covers:
- category query-param server-side filtering
- total field reflects DB count, not returned page size
"""

import json
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


def _insert_run(db: Path, repository_id: str = "repo-test") -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO ingestion_runs"
            " (run_id, repository_id, canonical_url, status, started_at)"
            " VALUES (?, ?, ?, ?, ?)",
            ("run-1", repository_id, "https://github.com/x/y", "COMPLETED", "2024-01-01"),
        )


def _insert_commit_with_analysis(
    db: Path,
    *,
    sha: str,
    category: str,
    repository_id: str = "repo-test",
    date: str = "2024-01-01T10:00:00",
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO commit_facts"
            " (repository_id, sha, committed_at, message, author_name,"
            "  committer_name, parent_shas, author_email)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (repository_id, sha, date, f"{category}: do thing", "Alice", "Alice", "[]", ""),
        )
        analysis: dict[str, object] = {
            "commit_sha": sha,
            "category": category,
            "summary": f"A {category} commit",
            "risk_level": "LOW",
            "intent": None,
            "intent_is_inferred": False,
            "affected_components": [],
            "confidence": 0.9,
            "evidence": [],
            "limitations": [],
        }
        conn.execute(
            "INSERT OR IGNORE INTO commit_analyses"
            " (repository_id, commit_sha, data)"
            " VALUES (?, ?, ?)",
            (repository_id, sha, json.dumps(analysis)),
        )


# ---------------------------------------------------------------------------
# Test 1: total reflects DB count, not returned page size
# ---------------------------------------------------------------------------


def test_commits_total_reflects_db_count_not_page_size(tmp_path: Path) -> None:
    """GET /commits total = total rows in DB, not capped by limit.

    With 5 analyzed commits and limit=2, total should be 5.
    """
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_run(db)
    for i in range(5):
        _insert_commit_with_analysis(
            db, sha=f"sha{i:03d}", category="FEATURE", date=f"2024-01-0{i + 1}T10:00:00"
        )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/repos/repo-test/commits?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["commits"]) == 2, "page should respect limit"
    assert body["total"] == 5, (
        f"total should reflect full DB count (5), not page size; got {body['total']}"
    )


# ---------------------------------------------------------------------------
# Test 2: category filter returns only matching commits
# ---------------------------------------------------------------------------


def test_commits_category_filter_returns_only_matching(tmp_path: Path) -> None:
    """GET /commits?category=DOCS returns only DOCS commits.

    Inserts 3 DOCS and 2 FEATURE commits; filter should return exactly 3.
    """
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_run(db)
    for i in range(3):
        _insert_commit_with_analysis(db, sha=f"docs{i}", category="DOCS")
    for i in range(2):
        _insert_commit_with_analysis(db, sha=f"feat{i}", category="FEATURE")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/repos/repo-test/commits?category=DOCS")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3, f"Expected 3 DOCS commits, got total={body['total']}"
    assert len(body["commits"]) == 3
    for c in body["commits"]:
        assert c["category"] == "DOCS", f"Got non-DOCS commit: {c}"


# ---------------------------------------------------------------------------
# Test 3: category filter total is filtered count, not overall count
# ---------------------------------------------------------------------------


def test_commits_category_filter_total_is_filtered_count(tmp_path: Path) -> None:
    """GET /commits?category=BUGFIX total counts only BUGFIX, not all commits."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_run(db)
    for i in range(2):
        _insert_commit_with_analysis(db, sha=f"bug{i}", category="BUGFIX")
    for i in range(10):
        _insert_commit_with_analysis(db, sha=f"oth{i}", category="CHORE")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/repos/repo-test/commits?category=BUGFIX&limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["commits"]) == 2


# ---------------------------------------------------------------------------
# AC-4: dual-audience summary fields surfaced via API
# ---------------------------------------------------------------------------


def _insert_commit_with_dual_analysis(
    db: Path,
    *,
    sha: str,
    summary_beginner: str,
    summary_expert: str,
    repository_id: str = "repo-test",
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO commit_facts"
            " (repository_id, sha, committed_at, message, author_name,"
            "  committer_name, parent_shas, author_email)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                repository_id,
                sha,
                "2024-01-01T10:00:00",
                "feat: add thing",
                "Alice",
                "Alice",
                "[]",
                "",
            ),
        )
        analysis: dict[str, object] = {
            "commit_sha": sha,
            "category": "FEATURE",
            "summary": summary_expert,
            "summary_beginner": summary_beginner,
            "summary_expert": summary_expert,
            "risk_level": "LOW",
            "intent": None,
            "intent_is_inferred": False,
            "affected_components": [],
            "confidence": 0.9,
            "evidence": [],
            "limitations": [],
        }
        conn.execute(
            "INSERT OR IGNORE INTO commit_analyses"
            " (repository_id, commit_sha, data)"
            " VALUES (?, ?, ?)",
            (repository_id, sha, json.dumps(analysis)),
        )


def test_commits_endpoint_returns_dual_summary_fields(tmp_path: Path) -> None:
    """GET /commits includes summary_beginner and summary_expert when present."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_run(db)
    _insert_commit_with_dual_analysis(
        db,
        sha="dual1",
        summary_beginner="Plain explanation",
        summary_expert="Refactored auth flow",
    )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/repos/repo-test/commits")
    assert resp.status_code == 200
    commits = resp.json()["commits"]
    assert len(commits) == 1
    c = commits[0]
    assert c["summary_beginner"] == "Plain explanation", f"Got {c.get('summary_beginner')!r}"
    assert c["summary_expert"] == "Refactored auth flow", f"Got {c.get('summary_expert')!r}"


def test_commits_endpoint_returns_none_for_legacy_analysis_without_dual_fields(
    tmp_path: Path,
) -> None:
    """GET /commits returns summary_beginner=null for pre-feature analyses."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_run(db)
    _insert_commit_with_analysis(db, sha="legacy1", category="CHORE")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/repos/repo-test/commits")
    assert resp.status_code == 200
    commits = resp.json()["commits"]
    assert len(commits) == 1
    c = commits[0]
    assert c["summary_beginner"] is None
    assert c["summary_expert"] is None
