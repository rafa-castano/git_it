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
    """Create all tables needed by the analyze/ingest endpoints."""
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


def test_estimate_returns_correct_counts(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
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

    _init_db(_db_path(tmp_path))
    client = TestClient(create_app(project_root=tmp_path))
    body = client.get("/api/repos/repo-abc/analyze/estimate").json()
    assert body["estimated_narrative_cost_usd"] == 0.0


def test_estimate_zero_calls_when_all_analyzed(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
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


def test_analyze_returns_analyzing_status(tmp_path: Path) -> None:
    from git_it.api.app import create_app

    db = _db_path(tmp_path)
    _init_db(db)
    _insert_commit(db, sha="aaa111")

    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.post("/api/repos/repo-abc/analyze", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ANALYZING"


def test_analyze_accepts_any_litellm_model(tmp_path: Path) -> None:
    from git_it.api.app import create_app

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
    from git_it.api.app import create_app

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
