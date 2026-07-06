# MCP Setup

This page describes how MCP servers are configured for Git It **development**
(the consumer side, `docs/specs/006-mcp-strategy.md`) under least privilege. See
`docs/mcp/servers.md` for the enabled server list and `docs/mcp/security.md`
for the underlying security rules this setup follows.

For the MCP server Git It itself **exposes** (`git-it mcp`), see the
"Git It as an MCP provider" section of `docs/mcp/servers.md` and
`docs/specs/011-mcp-server-exposure.md` instead — that is a separate, already
implemented feature, not a development-tooling MCP server.

## Principles

Every server below is configured to the minimum access it needs:

- **Read-only unless a spec explicitly approves writes.**
- **Scoped, never broad.** No server is granted the user's home directory or
  parent directories above the repository.
- **No secrets in MCP config.** Tokens and credentials are read from
  environment variables at the process level, never written into an MCP
  server's config file or command-line arguments.
- **Public-read GitHub access only**, not a token with elevated org/repo
  permissions.

## Filesystem MCP

Configure the server's allowed directory roots as explicit workspace
subdirectories only — never the repository root, since secret-bearing files
(`.env`, `.env.*`) live at that level:

```
.claude
.codex
.prompts
ADR
docs
evals
specs
src
tests
```

Do not add `.git`, `.venv`/virtual environments, browser profiles, SSH keys,
or cloud credential directories to this list. Any future addition to this
list must document why the directory is needed, whether it can contain
secrets, and whether write access is required (see "Contributor
expectations" in `docs/mcp/security.md`).

## Git MCP

Configure Git MCP scoped to the Git It repository only, with read-only
intent: status, diffs (staged/unstaged), log, `show`, and branch inspection
are allowed. Do not configure or rely on any push/commit/reset/checkout
capability the server implementation might expose — `AGENTS.md`'s "Git MCP
policy" treats those as forbidden regardless of what the underlying tool can
technically do.

## GitHub MCP

Use a public-read token (or no token, for unauthenticated public read
access) via an environment variable — never hard-code a token in MCP
configuration. Do not enable write-capable GitHub toolsets (issue/PR
creation, repository administration) for development use.

## PostgreSQL MCP

Point the server at a read-only database role/connection string supplied
through an environment variable (e.g. `DATABASE_URL` pointed at a read-only
user). Write access is only granted when a specific spec explicitly approves
it for that workflow; the default for AI-driven database inspection is
always read-only.

## Context7 / Exa (or equivalent search) MCP

These serve public documentation and public web content only. No
repository-specific or secret configuration is required; no write capability
applies.

## Playwright MCP

Scope browser automation to `localhost` targets used for local UI
validation of the Git It dashboard. Do not configure it for unrestricted
external browsing.

## Token and secret handling

- All tokens/credentials are supplied via environment variables at process
  launch, consistent with `CODEX.md`'s security baseline ("Protect API keys
  and tokens with environment variables", "Do not log secrets").
- Never commit an MCP client configuration file that embeds a raw token.
- If a setup step requires a token, document which environment variable it
  reads — do not paste example tokens into this file or into `docs/mcp/servers.md`.

## Verifying a new or changed server

Before enabling a new MCP server or widening an existing one's access:

1. Add or update its row in `docs/mcp/servers.md` (purpose, access level,
   write-allowed).
2. Confirm the access level matches the least-privilege rules in
   `docs/mcp/security.md`.
3. Document the justification (why, secret exposure risk, write necessity)
   per `docs/mcp/security.md`'s "Contributor expectations" section.
4. Cross-check against `docs/specs/006-mcp-strategy.md` AC-7.
