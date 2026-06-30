"""Spec 011 AC-1 — `git-it mcp` subcommand runs the read-only MCP stdio server."""

from pathlib import Path

import pytest


def test_mcp_subcommand_runs_stdio_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_run(self: object, transport: str = "stdio") -> None:
        calls["transport"] = transport

    # Capture the run() call so the test does not block on a real stdio loop.
    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", fake_run)

    from git_it.repository_ingestion.interfaces.cli import main

    rc = main(["mcp"], project_root=tmp_path)

    assert rc == 0
    assert calls["transport"] == "stdio"
