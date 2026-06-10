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