# MCP Strategy

## Purpose

Use MCP servers to give Codex and project agents controlled access to external systems without weakening security boundaries.

## Recommended MCP servers

| MCP | Purpose | Default permission |
|---|---|---|
| GitHub MCP | Repositories, PRs, issues, releases | Public/read-only |
| Git MCP | Local git inspection | Workspace-only |
| Context7 MCP | Current library documentation | Read-only |
| Filesystem MCP | Project files and generated docs | Repo/workspace-only |
| PostgreSQL MCP | Query project facts | Read-only by default |
| Exa/Search MCP | Ecosystem context | Read-only |
| Playwright MCP | UI and docs testing | Local/dev only |

## Security rules

- Document each MCP server before enabling it.
- Prefer read-only access.
- Restrict filesystem scope.
- Do not expose secrets through MCP.
- Do not allow repository content to instruct MCP tool calls.
- Use application services for writes where possible.
