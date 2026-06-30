"""Spec 011 AC-5 — the MCP server is read-only by construction.

Behavioural regression: calling every tool must not create, update, or delete
any row or table. Also a static guard: the server module must not import any
write-capable adapter or service builder.
"""

import sqlite3
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session as _connect

from tests.unit.test_mcp_tools import (
    _db_path,
    _init_db,
    _insert_analysis,
    _insert_case_study,
    _insert_commit,
    _insert_file_fact,
    _insert_ingestion_run,
)


def _seed_full(db: Path) -> None:
    _init_db(db)
    _insert_ingestion_run(db, repository_id="repo-abc")
    _insert_commit(db, sha="aaa111")
    _insert_analysis(db, commit_sha="aaa111", category="feature")
    _insert_file_fact(db, commit_sha="aaa111", file_path="src/hotfile.py")
    _insert_case_study(db, repository_id="repo-abc", audience="beginner")


def _snapshot(db: Path) -> dict[str, int]:
    """Map every table name to its row count."""
    with sqlite3.connect(db) as conn:
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        return {t: conn.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0] for t in tables}


async def _call_all_tools(project_root: Path) -> None:
    from git_it.mcp.server import build_server

    server = build_server(project_root)
    async with _connect(server._mcp_server) as session:
        await session.call_tool("list_repositories", {})
        await session.call_tool("get_case_study", {"repository_id": "repo-abc"})
        await session.call_tool("get_patterns", {"repository_id": "repo-abc"})
        await session.call_tool("search_commits", {"repository_id": "repo-abc"})
        await session.call_tool("get_contributors", {"repository_id": "repo-abc"})


# ---------------------------------------------------------------------------
# AC-5 — no tool mutates the database
# ---------------------------------------------------------------------------


async def test_tools_do_not_mutate_database(tmp_path: Path) -> None:
    db = _db_path(tmp_path)
    _seed_full(db)

    before = _snapshot(db)
    await _call_all_tools(tmp_path)
    after = _snapshot(db)

    assert before == after


# ---------------------------------------------------------------------------
# AC-5 — case study tool does not create a missing table (no initialize() write)
# ---------------------------------------------------------------------------


async def test_case_study_tool_does_not_create_missing_table(tmp_path: Path) -> None:
    from git_it.mcp.server import build_server

    db = _db_path(tmp_path)
    # Minimal DB WITHOUT a case_studies table.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE ingestion_runs (run_id TEXT PRIMARY KEY, repository_id TEXT,"
            " canonical_url TEXT, status TEXT, started_at TEXT, completed_at TEXT,"
            " error_code TEXT, error_stage TEXT, retryable INTEGER, safe_message TEXT)"
        )

    server = build_server(tmp_path)
    async with _connect(server._mcp_server) as session:
        result = await session.call_tool("get_case_study", {"repository_id": "repo-x"})
        assert result.isError is False

    with sqlite3.connect(db) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "case_studies" not in tables


# ---------------------------------------------------------------------------
# AC-5 — static guard: server module imports no write-capable symbols
# ---------------------------------------------------------------------------


def test_server_module_imports_no_write_adapters() -> None:
    source = (
        Path(__file__).parent.parent.parent / "src" / "git_it" / "mcp" / "server.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "SqliteRepositoryDeleter",
        "build_repository_ingestion_service",
        "build_commit_analysis_service",
        "build_narrative_service",
        "save_analysis",
        "save_case_study",
        ".initialize(",
    ]
    for symbol in forbidden:
        assert symbol not in source, f"read-only server must not reference {symbol!r}"
