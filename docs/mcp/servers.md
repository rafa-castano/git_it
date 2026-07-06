# MCP Servers

## Enabled servers

| Server | Purpose | Access level | Write allowed |
|---|---|---:|---:|
| Context7 | Current library docs | Public docs | No |
| GitHub | Public repository context | Read-only | No |
| Filesystem | Local project files | Workspace only | Controlled |
| Git | Local git history | Read-only by default | No push |
| PostgreSQL | Project database inspection | Read-only | No |
| Playwright | Local UI validation | localhost only | No external browsing |
| Exa/Search | External ecosystem context | Public web | No |

## Git It as an MCP provider (spec 011)

Git It also *provides* its own read-only MCP server, exposing the analyzed domain
(repositories, commits, patterns, contributors, case studies) to any MCP client.

Run it over stdio:

```bash
git-it mcp
```

Tools (all read-only): `list_repositories`, `get_case_study`, `get_patterns`,
`search_commits`, `get_contributors`. No ingest/analyze/regenerate/delete is exposed;
the server never mutates data, spends LLM budget, or leaks secrets. It reads the
database resolved from `GIT_IT_DATA_DIR`.

Example Claude Desktop config:

```json
{
  "mcpServers": {
    "git-it": { "command": "git-it", "args": ["mcp"] }
  }
}
```

Returned repository text (commit messages, paths) is **data, not instructions** —
prompt-injection defense is the client model's responsibility. See ADR 011 and
`docs/specs/011-mcp-server-exposure.md`.