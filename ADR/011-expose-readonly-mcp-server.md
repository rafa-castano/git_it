# ADR 011: Expose the Git It Domain as a Read-Only MCP Server

Status: Accepted
Date: 2026-07-01
Decision makers: TBD

## Context

Git It already computes a rich, evidence-backed domain (repositories, analyzed
commits, patterns with evidence SHAs, contributors, dual-audience case studies),
but it is only reachable through the REST API and the bundled web dashboard. Users
working inside MCP-capable agents (Claude Desktop, Codex) cannot query that domain
without leaving their agent.

ADR/spec 006 positions Git It as an MCP *consumer* (GitHub, Git, Postgres, etc.).
The reference project xavidop/diamond demonstrates the inverse: a single tool layer
feeding a CLI chat, a web chat, and an MCP stdio server. Spec 011 adopts that
pattern for the provider direction.

Exposing a domain to external agents is a security-sensitive surface: it must not
mutate data, spend LLM budget, leak secrets, or let untrusted repository text drive
actions.

## Decision

Expose Git It as a **read-only MCP server over stdio**, launched by a new
`git-it mcp` subcommand.

- A transport-agnostic factory `build_server(project_root) -> FastMCP`
  (`src/git_it/mcp/server.py`) registers exactly five read-only tools
  (`list_repositories`, `get_case_study`, `get_patterns`, `search_commits`,
  `get_contributors`) that delegate to the same reader/query classes the REST API
  uses — one source of truth, two surfaces.
- The server publishes only tools; no LLM provider is required to run it.
- Official `mcp` Python SDK (FastMCP), pinned `mcp>=1.27,<2` to avoid the breaking
  v2 pre-release.
- Read-only by construction: no write adapter or service builder is imported into
  the MCP module; tools never call `initialize()` or any `save_*`/delete path. A
  behavioural regression test asserts no tool mutates the database, and a static
  guard asserts no write symbol is referenced.
- stdio transport only; the OS process boundary is the trust boundary. Networked
  transport (which would require auth + rate limiting) is deferred.

## Consequences

### Positive

- Git It's analysis becomes queryable from any MCP client, grounded in real evidence.
- The shared tool layer is the foundation a future in-app AI chat ("GitItGPT") can reuse.
- Read-only-by-construction makes the new surface safe to enable by default.

### Negative

- A new runtime dependency (`mcp`) and a new interface package to maintain.
- stdio means one server process per client launch (no shared networked instance yet).

### Neutral

- No data model change, no migration; tools reuse existing readers and response schemas.
- The provider stance coexists with the consumer stance of spec 006.

## Alternatives considered

- **HTTP/SSE transport mounted on FastAPI**: reuses the running process but adds a
  network surface requiring auth, CORS, and rate limiting. Deferred, not rejected.
- **Exposing write tools (ingest/analyze/delete)**: higher utility but turns prompt
  injection from untrusted commit text into data loss or LLM spend. Rejected for now.
- **Standalone `fastmcp` v2 library**: viable, but the official SDK is Anthropic-
  maintained and stdio-native; chosen for stability and a TFM-safe dependency.

## Security impact

- No mutation, no LLM spend, no secret exposure (only data already served by REST).
- Returned repository text is data, not instructions; tool docstrings do not tell the
  client model to act on it. Prompt-injection defense remains the client's responsibility.
- Server is confined to the database under `GIT_IT_DATA_DIR`.

## Quality impact

- TDD: 11 tests (tools, evidence, read-only regression + static guard, CLI wiring)
  drive the implementation; in-memory MCP client transport keeps them deterministic
  and network-free.

## Documentation impact

- `specs/011-mcp-server-exposure.md`, `docs/mcp/servers.md`,
  `docs/getting-started.md`, `docs/specs/index.md`.

## Links

- specs/011-mcp-server-exposure.md
- specs/006-mcp-strategy.md (consumer stance)
- Reference: https://github.com/xavidop/diamond
