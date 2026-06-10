# Threat Model

## Assets

- GitHub tokens.
- LLM API keys.
- Database credentials.
- Analyzed repository data.
- Generated analysis outputs.
- User accounts when added.
- Local filesystem workspace.

## Trust boundaries

- User input to API.
- Public GitHub content to ingestion system.
- Repository content to LLM prompts.
- LLM output to application storage.
- MCP tools to external systems.
- Worker sandbox to host system.

## Main threats

- Prompt injection through repository content.
- Accidental execution of untrusted repository code.
- SSRF via external URLs.
- Secret leakage in logs.
- Over-permissive MCP access.
- Dependency supply-chain risk.
- False or unsupported generated claims.
- Denial of service through huge repositories.

## Required mitigations

- Treat repository content as data.
- Restrict workspace access.
- Keep ingestion clones and run artifacts under `.data/git-it/ingestion/`.
- Use generated identifiers for repository cache and ingestion run paths.
- Never use owner, repo, branch, ref, or other external strings directly as filesystem paths.
- Validate repository URLs before invoking Git tooling.
- Accept only strict public `https://github.com/{owner}/{repo}` style URLs for MVP ingestion.
- Reject HTTP, SSH, `git://`, `file://`, GitHub Enterprise, owner-only, tree, pull-request, and arbitrary remote URLs.
- Add repository size and timeout limits.
- Use bare clone/fetch for repository ingestion by default.
- Do not checkout analyzed repositories by default.
- Do not initialize submodules or fetch Git LFS blobs by default.
- Do not store or return binary file content as diff text.
- Apply ingestion safety restrictions to on-demand full diff retrieval and cache refresh.
- Clean temporary ingestion run directories after terminal statuses.
- Do not persist or log raw commit author or committer email addresses by default.
- Prefer GitHub user ID or node ID for high-confidence contributor identity.
- Use HMAC-SHA256 with `GIT_IT_IDENTITY_PEPPER` only as a deterministic fallback contributor email key.
- Do not store `GIT_IT_IDENTITY_PEPPER` in repository files.
- Do not use bcrypt or Argon2 for contributor identity correlation.
- Treat commit signature verification as provenance evidence, not proof of developer intent or absolute authorship.
- Keep user-facing ingestion failures free of secrets, raw emails, credential-bearing URLs, stack traces, and unmarked repository content.
- Use read-only tokens by default.
- Redact secrets from logs.
- Validate LLM output schemas.
- Require evidence and limitations.
- Scan dependencies.
- Do not execute repository code by default.
