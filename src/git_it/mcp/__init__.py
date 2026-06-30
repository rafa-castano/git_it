"""Read-only Model Context Protocol server exposure for Git It (spec 011).

Exposes the already-analyzed domain (repositories, commits, patterns,
contributors, case studies) as MCP tools backed by the same read services the
REST API uses. Read-only: no ingest, analyze, regenerate, or delete.
"""

from git_it.mcp.server import build_server

__all__ = ["build_server"]
