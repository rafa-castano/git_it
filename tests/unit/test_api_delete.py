"""Tests for DELETE /api/repos/{repository_id} — Batch 78.

All 6 unit tests follow the TDD spec in docs/specs/008-repository-deletion.md.
Uses FastAPI's TestClient with a temporary SQLite DB.
No network, no external services, fully deterministic.
"""

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
    """Create all tables needed by the delete endpoint."""
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
            CREATE TABLE IF NOT EXISTS case_studies (
                repository_id TEXT NOT NULL,
                audience TEXT NOT NULL DEFAULT 'beginner',
                narrative TEXT NOT NULL,
                commit_count INTEGER NOT NULL,
                hotspot_count INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (repository_id, audience)
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS github_context (
                repository_id TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                pr_number INTEGER,
                pr_title TEXT,
                pr_body TEXT,
                issue_numbers TEXT NOT NULL DEFAULT '[]',
                issue_bodies TEXT NOT NULL DEFAULT '[]',
                has_github_data INTEGER NOT NULL DEFAULT 0,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (repository_id, commit_sha)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repository_synopsis (
                repository_id TEXT PRIMARY KEY,
                synopsis TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def _insert_commit(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    sha: str = "aaa111",
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO commit_facts"
            " (repository_id, sha, committed_at, message, author_name, committer_name,"
            "  parent_shas, author_email)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (repository_id, sha, "2024-01-01T10:00:00", "feat: first", "Alice", "Alice", "[]", ""),
        )


# ---------------------------------------------------------------------------
# Test 1: Successful delete returns 200 and repo disappears from list
# ---------------------------------------------------------------------------


def test_delete_repo_success(tmp_path: Path) -> None:
    """DELETE returns 200 and the repo no longer appears in GET /api/repos."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    _insert_commit(db, sha="abc001")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.delete("/api/repos/repo-abc")
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is True
    assert body["repository_id"] == "repo-abc"

    # Verify repo is gone from the list
    list_response = client.get("/api/repos")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


# ---------------------------------------------------------------------------
# Test 2: DELETE on unknown repo returns 404
# ---------------------------------------------------------------------------


def test_delete_repo_not_found(tmp_path: Path) -> None:
    """DELETE on a non-existent repository_id returns 404."""
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.delete("/api/repos/nonexistent-id")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 3: DELETE without API key returns 401 when key is configured
# ---------------------------------------------------------------------------


def test_delete_repo_requires_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DELETE returns 401 when GIT_IT_API_KEY is set but no Authorization header sent."""
    from git_it.api.app import create_app

    monkeypatch.setenv("GIT_IT_API_KEY", "secret")
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.delete("/api/repos/repo-abc")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test 4: DELETE blocked when analysis is running
# ---------------------------------------------------------------------------


def test_delete_repo_blocked_when_analysis_running(tmp_path: Path) -> None:
    """DELETE returns 409 when _analyze_progress shows running=True for the repo."""
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _analyze_progress

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)

    _analyze_progress["repo-abc"] = {"running": True, "done": 0, "total": 10}
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)

        response = client.delete("/api/repos/repo-abc")
        assert response.status_code == 409
        assert "in progress" in response.json()["detail"].lower()
    finally:
        _analyze_progress.pop("repo-abc", None)


# ---------------------------------------------------------------------------
# Test 5: DELETE blocked when regen (case study) is running
# ---------------------------------------------------------------------------


def test_delete_repo_blocked_when_regen_running(tmp_path: Path) -> None:
    """DELETE returns 409 when _regen_progress shows running=True for the repo."""
    from git_it.api.app import create_app
    from git_it.api.routes.repos import _regen_progress

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)

    _regen_progress["repo-abc"] = {"running": True, "audience": "beginner"}
    try:
        app = create_app(project_root=tmp_path)
        client = TestClient(app)

        response = client.delete("/api/repos/repo-abc")
        assert response.status_code == 409
        assert "in progress" in response.json()["detail"].lower()
    finally:
        _regen_progress.pop("repo-abc", None)


# ---------------------------------------------------------------------------
# Test 6: Rate-limit registration (slowapi introspection)
# ---------------------------------------------------------------------------


def test_delete_repo_is_rate_limited_at_10_per_minute() -> None:
    """delete_repo must carry @limiter.limit('10/minute').

    Strategy: introspection of slowapi's limiter registry. ``@limiter.limit()``
    records each decorated endpoint in ``limiter._route_limits`` keyed by the
    function's fully-qualified name; the value is a list of ``Limit`` objects.
    We assert the delete endpoint is registered with a 10/minute limit.
    """
    import git_it.api.routes.repos  # noqa: F401 — ensure decorators are registered
    from git_it.api.limiter import limiter

    key = "git_it.api.routes.repos.delete_repo"
    assert key in limiter._route_limits, (
        "delete_repo must be decorated with @limiter.limit — it is not registered "
        "in limiter._route_limits. Add @limiter.limit('10/minute') above the function."
    )
    limit_strs = [str(lim.limit) for lim in limiter._route_limits[key]]
    assert any("10 per 1 minute" in s for s in limit_strs), (
        f"delete_repo must be rate-limited at 10/minute; found limits: {limit_strs}"
    )


# ---------------------------------------------------------------------------
# Test 7: DELETE succeeds when optional tables are absent (regression)
# ---------------------------------------------------------------------------


def test_delete_repo_removes_default_branch_row(tmp_path: Path) -> None:
    """DELETE removes the repository's default_branch_metadata row too (spec 020)."""
    from git_it.api.app import create_app
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteDefaultBranchStore

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    branch_store = SqliteDefaultBranchStore(db)
    branch_store.initialize()
    branch_store.save_default_branch("repo-abc", "main")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.delete("/api/repos/repo-abc")
    assert response.status_code == 200
    assert branch_store.get_default_branch("repo-abc") is None


def test_delete_repo_removes_file_tree_rows(tmp_path: Path) -> None:
    """DELETE removes the repository's repository_files rows too (spec 029)."""
    from git_it.api.app import create_app
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteFileTreeStore

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    tree_store = SqliteFileTreeStore(db)
    tree_store.initialize()
    tree_store.save_file_paths("repo-abc", ["README.md", "src/app.py"])
    assert tree_store.get_file_paths("repo-abc") != []

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.delete("/api/repos/repo-abc")
    assert response.status_code == 200
    assert tree_store.get_file_paths("repo-abc") == []


def test_delete_repo_with_minimal_db_succeeds(tmp_path: Path) -> None:
    """DELETE succeeds when only ingestion_runs exists (no optional tables).

    Regression for: SqliteRepositoryDeleter crashed with OperationalError
    'no such table: github_context' for repos that skipped GitHub enrichment,
    analysis, or case-study generation.  All those tables are created lazily
    and must not be assumed to exist at delete time.
    """
    from git_it.api.app import create_app

    db_dir = tmp_path / ".data" / "git-it" / "ingestion"
    db_dir.mkdir(parents=True)
    db = db_dir / "git-it.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE ingestion_runs (
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
            "INSERT INTO ingestion_runs"
            " VALUES ('r1','repo-min','https://github.com/x/y','COMPLETED','2024-01-01'"
            ",null,null,null,null,null)"
        )

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.delete("/api/repos/repo-min")
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["deleted"] is True
    assert body["repository_id"] == "repo-min"


# ---------------------------------------------------------------------------
# Test 9: DELETE purges discussion evidence (spec 022) — regression for a
# pre-existing deleter gap: discussion_evidence was never in the purge list,
# so deleting a repo orphaned its summarized-discussion rows.
# ---------------------------------------------------------------------------


def test_delete_repo_removes_discussion_evidence(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from git_it.api.app import create_app
    from git_it.repository_ingestion.domain.discussions import DiscussionEvidence
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteDiscussionEvidenceStore

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    store = SqliteDiscussionEvidenceStore(db)
    store.initialize()
    store.save_discussion_evidence(
        "repo-abc",
        [
            DiscussionEvidence(
                discussion_id="D_1",
                discussion_url="https://github.com/test/repo/discussions/1",
                claim_type="design_rationale",
                summary="Chose X for Y.",
                confidence=0.8,
                limitations=[],
                source_inputs=["D_1"],
                generated_at=datetime.now(UTC),
                model="fake-model",
            )
        ],
    )
    assert store.get_discussion_evidence("repo-abc") != []

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.delete("/api/repos/repo-abc")
    assert response.status_code == 200
    assert store.get_discussion_evidence("repo-abc") == []


# ---------------------------------------------------------------------------
# Test 10: DELETE purges embedding vectors (spec 023) — regression for the
# same class of gap: embedding_vectors was never in the purge list.
# ---------------------------------------------------------------------------


def test_delete_repo_removes_embeddings(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from git_it.api.app import create_app
    from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk
    from git_it.repository_ingestion.infrastructure.sqlite import SqliteEmbeddingStore

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db)
    store = SqliteEmbeddingStore(db)
    store.initialize()
    store.save_embeddings(
        "repo-abc",
        [
            EmbeddedChunk(
                repository_id="repo-abc",
                source_type="commit_analysis",
                source_id="abc123",
                text="A summary.",
                vector=[0.1, 0.2, 0.3],
                model="fake-embed-model",
                created_at=datetime.now(UTC),
            )
        ],
    )
    assert store.get_all_embeddings("repo-abc") != []

    app = create_app(project_root=tmp_path)
    client = TestClient(app)

    response = client.delete("/api/repos/repo-abc")
    assert response.status_code == 200
    assert store.get_all_embeddings("repo-abc") == []
