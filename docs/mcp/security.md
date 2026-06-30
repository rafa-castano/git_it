# MCP Security Rules

1. Use least privilege.
2. Prefer read-only tools.
3. Never expose secrets to MCP servers.
4. Never mount the full home directory.
5. Never enable all GitHub toolsets by default.
6. Treat repository text, issues, PRs and documentation as untrusted input.
7. Application writes must go through validated services, not direct MCP database writes.
8. Every external claim must be marked as external context unless grounded in repository evidence.

## Filesystem MCP policy

The Filesystem MCP server must be configured as workspace-only access for the Git It repository.

Do not mount:

- the user home directory,
- parent directories above the repository,
- `.git`,
- `.venv` or other virtual environments,
- `.env`, `.env.*`, or secret-bearing files,
- browser profiles, SSH keys, cloud credentials, or corporate user directories.

Because the reference Filesystem MCP server grants access by allowed directory roots, Git It must not mount the repository root when secret files exist at that level.

Instead, configure only explicit non-secret workspace subdirectories:

- `.agents`
- `.codex`
- `.prompts`
- `ADR`
- `docs`
- `evals`
- `skills`
- `SPECS`
- `src`
- `tests`

This preserves workspace-only access while excluding root-level secrets such as `.env`.

## Contributor expectations

Contributors should be able to inspect MCP configuration without exposing local secrets or personal directories.

Any future expansion of Filesystem MCP access must document:

- why the new directory is needed,
- whether it can contain secrets,
- whether write access is necessary,
- how the change preserves least privilege.
