"""Spec 011 — read-only MCP server tools.

These tests drive the MCP tool layer (`git_it.mcp.server.build_server`) through
the official SDK's in-memory client transport. No network, no stdio process,
fully deterministic. The DB is seeded with the same raw SQLite helpers the REST
API tests use.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session as _connect

# ---------------------------------------------------------------------------
# DB seeding helpers (mirrors tests/unit/test_api_repos.py)
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "list_repositories",
    "get_case_study",
    "get_patterns",
    "search_commits",
    "get_contributors",
}


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
            CREATE TABLE IF NOT EXISTS case_studies (
                repository_id TEXT NOT NULL,
                audience      TEXT NOT NULL DEFAULT 'beginner',
                narrative     TEXT NOT NULL,
                commit_count  INTEGER NOT NULL,
                hotspot_count INTEGER NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
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
    summary: str = "Added feature X",
) -> None:
    data = json.dumps(
        {
            "commit_sha": commit_sha,
            "summary": summary,
            "category": category,
            "risk_level": "low",
            "affected_components": [],
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
    audience: str = "beginner",
    narrative: str = "# Case Study\n\nThis is the narrative.",
    commit_count: int = 5,
    hotspot_count: int = 2,
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO case_studies"
            " (repository_id, audience, narrative, commit_count, hotspot_count)"
            " VALUES (?, ?, ?, ?, ?)",
            (repository_id, audience, narrative, commit_count, hotspot_count),
        )


def _insert_file_fact(
    db: Path,
    *,
    repository_id: str = "repo-abc",
    commit_sha: str = "aaa111",
    file_path: str = "src/hotfile.py",
    insertions: int = 5,
    deletions: int = 3,
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO file_facts"
            " (repository_id, commit_sha, file_path, insertions, deletions)"
            " VALUES (?, ?, ?, ?, ?)",
            (repository_id, commit_sha, file_path, insertions, deletions),
        )


# ---------------------------------------------------------------------------
# In-memory client helpers
# ---------------------------------------------------------------------------


def _payload(result: object) -> dict[str, Any]:
    """Parse a CallToolResult into the tool's JSON dict (text content)."""
    if getattr(result, "isError", False):
        text = result.content[0].text if result.content else "<no content>"  # type: ignore[attr-defined]
        raise AssertionError(f"tool returned an error: {text}")
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and "result" not in structured:
        return structured
    content = result.content[0]  # type: ignore[attr-defined]
    parsed: dict[str, Any] = json.loads(content.text)
    return parsed


async def _list_tool_names(project_root: Path) -> set[str]:
    from git_it.mcp.server import build_server

    server = build_server(project_root)
    async with _connect(server._mcp_server) as session:
        listed = await session.list_tools()
        return {t.name for t in listed.tools}


async def _call(project_root: Path, name: str, args: dict | None = None) -> dict:
    from git_it.mcp.server import build_server

    server = build_server(project_root)
    async with _connect(server._mcp_server) as session:
        result = await session.call_tool(name, args or {})
        return _payload(result)


# ---------------------------------------------------------------------------
# AC-3 — exactly five read-only tools registered
# ---------------------------------------------------------------------------


async def test_server_registers_exactly_five_readonly_tools(tmp_path: Path) -> None:
    db = _db_path(tmp_path)
    _init_db(db)
    names = await _list_tool_names(tmp_path)
    assert names == EXPECTED_TOOLS


# ---------------------------------------------------------------------------
# AC-3 — list_repositories returns seeded repositories
# ---------------------------------------------------------------------------


async def test_list_repositories_returns_seeded_repo(tmp_path: Path) -> None:
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(
        db, repository_id="repo-abc", canonical_url="https://github.com/test/repo"
    )
    _insert_commit(db, repository_id="repo-abc", sha="aaa111")
    _insert_commit(db, repository_id="repo-abc", sha="bbb222", committed_at="2024-01-02T10:00:00")

    body = await _call(tmp_path, "list_repositories")
    assert body["total"] == 1
    repo = body["repos"][0]
    assert repo["repository_id"] == "repo-abc"
    assert repo["canonical_url"] == "https://github.com/test/repo"
    assert repo["commit_count"] == 2


# ---------------------------------------------------------------------------
# AC-4 — unknown repository_id returns a structured empty result, not an error
# ---------------------------------------------------------------------------


async def test_unknown_repository_returns_structured_empty(tmp_path: Path) -> None:
    db = _db_path(tmp_path)
    _init_db(db)

    body = await _call(tmp_path, "get_contributors", {"repository_id": "repo-does-not-exist"})
    assert body["contributors"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# AC-3 — get_case_study returns stored narrative + available audiences
# ---------------------------------------------------------------------------


async def test_get_case_study_returns_stored_narrative(tmp_path: Path) -> None:
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_case_study(
        db,
        repository_id="repo-cs",
        audience="beginner",
        narrative="# Engineering Case Study\n\nThis repo is fascinating.",
        commit_count=10,
        hotspot_count=3,
    )

    body = await _call(
        tmp_path, "get_case_study", {"repository_id": "repo-cs", "audience": "beginner"}
    )
    assert body["repository_id"] == "repo-cs"
    assert "fascinating" in body["narrative"]
    assert body["commit_count"] == 10
    assert "beginner" in body["available_audiences"]


# ---------------------------------------------------------------------------
# AC-3 (resolved) — unavailable audience is REPORTED, not generated (read-only)
# ---------------------------------------------------------------------------


async def test_get_case_study_unavailable_audience_reports_not_generates(tmp_path: Path) -> None:
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_case_study(db, repository_id="repo-cs", audience="beginner", narrative="Beginner text.")

    body = await _call(
        tmp_path, "get_case_study", {"repository_id": "repo-cs", "audience": "expert"}
    )
    # Expert was never generated → empty narrative, but availability is reported
    assert body["narrative"] == ""
    assert body["available_audiences"] == ["beginner"]


# ---------------------------------------------------------------------------
# AC-3 — search_commits honors category and limit filters
# ---------------------------------------------------------------------------


async def test_search_commits_honors_category_and_limit(tmp_path: Path) -> None:
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    for i in range(5):
        _insert_commit(db, sha=f"feat{i:03d}", committed_at=f"2024-01-{i + 1:02d}T10:00:00")
        _insert_analysis(db, commit_sha=f"feat{i:03d}", category="feature", summary=f"feature {i}")
    for i in range(3):
        _insert_commit(db, sha=f"fix{i:03d}", committed_at=f"2024-02-{i + 1:02d}T10:00:00")
        _insert_analysis(db, commit_sha=f"fix{i:03d}", category="bugfix", summary=f"fix {i}")

    body = await _call(
        tmp_path, "search_commits", {"repository_id": "repo-abc", "category": "feature"}
    )
    assert body["total"] == 5
    assert all(c["category"] == "feature" for c in body["commits"])

    limited = await _call(tmp_path, "search_commits", {"repository_id": "repo-abc", "limit": 2})
    assert len(limited["commits"]) == 2
    assert limited["total"] == 8  # full count, not page size


# ---------------------------------------------------------------------------
# AC-6 — get_patterns retains evidence commit SHAs for a hotspot
# ---------------------------------------------------------------------------


async def test_get_patterns_includes_evidence_shas(tmp_path: Path) -> None:
    db = _db_path(tmp_path)
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    for i in range(10):
        sha = f"sha{i:04d}"
        _insert_commit(db, sha=sha, committed_at=f"2024-01-{i + 1:02d}T10:00:00")
        _insert_file_fact(db, commit_sha=sha, file_path="src/hotfile.py")

    body = await _call(
        tmp_path, "get_patterns", {"repository_id": "repo-abc", "hotspot_threshold": 5}
    )
    assert body["repository_id"] == "repo-abc"
    hotspots = body["hotspots"]
    assert len(hotspots) >= 1
    top = hotspots[0]
    assert top["file_path"] == "src/hotfile.py"
    assert top["commit_count"] == 10
    assert len(top["evidence_commit_shas"]) >= 1  # interpretations carry evidence
