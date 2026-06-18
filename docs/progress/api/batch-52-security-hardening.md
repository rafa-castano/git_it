## Batch 52 — Security hardening

### Goal

Address all findings from the security agent review: prompt injection, env leakage, input validation, API authentication, rate limiting, MCP tool permissions, and dependency locking.

### What was added

**Prompt injection hardening:**
- `_SYSTEM_PROMPT` is now a clean invariant constant; `repo_context` is never appended to it
- `repo_context` injected into the user message body with explicit safety tags:
  `[REPO CONTEXT — AI-GENERATED SUMMARY, MAY CONTAIN UNTRUSTED REPOSITORY DATA]…[/REPO CONTEXT]`
- `CommitAnalysisClient.analyze_commit` protocol updated to accept explicit `system: str` parameter
- `InstructorCommitAnalysisAdapter` prepends `{"role": "system", "content": system}` to the message list

**Git subprocess env allowlist (`git.py`):**
- Replaced `dict(os.environ)` pass-through with an explicit allowlist:
  `HOME`, `USERPROFILE`, `PATH`, `SYSTEMROOT`, `TEMP`, `TMP`, `GIT_CONFIG_GLOBAL`, `GIT_EXEC_PATH`, `GIT_TEMPLATE_DIR`, `SSL_CERT_FILE`, `SSL_CERT_DIR`, `CURL_CA_BUNDLE`
- `ANTHROPIC_API_KEY`, `AWS_*`, and all other secrets are no longer forwarded to subprocess

**API authentication (`src/git_it/api/auth.py` — new):**
- `require_api_key` FastAPI dependency: checks `GIT_IT_API_KEY` env var
- If set, requires `Authorization: Bearer <key>`; missing or wrong key → 401
- Uses `secrets.compare_digest` (timing-safe comparison)
- If env var is not set, dependency is a no-op (dev mode)

**Rate limiting (`src/git_it/api/limiter.py` — new):**
- `slowapi.Limiter` instance with `get_remote_address` key function
- `POST /ingest`: 5 requests/minute
- `POST /analyze`: 10 requests/minute
- `SlowAPIMiddleware` registered in `app.py`

**Model allowlist:**
- `AnalyzeRequest.model` validated to `anthropic/claude-*` only via `@field_validator`

**Error message hardening:**
- Route error handlers expose `exc.error_code` (domain enum value), not `str(exc)` (may leak internals)

**Order parameter allowlist:**
- `order` query param changed from `str` to `Literal["newest", "oldest"]` in route signature

**MCP write tool enforcement (`.claude/settings.json`):**
- Denied: `mcp__git__git_add`, `mcp__git__git_commit`, `mcp__git__git_create_branch`, `mcp__git__git_checkout`, `mcp__git__git_reset`

**Dependency lockfile:**
- Added `uv.lock` to repository root via `uv lock`
- Added `slowapi>=0.1.9` to `pyproject.toml`

### Tests added

See batch 54 — auth enforcement tests written as part of TDD catch-up.

### Gotchas

- `secrets.compare_digest` requires both arguments to be the same type (str); `hmac.compare_digest` works on bytes or str — used the `secrets` wrapper
- When `GIT_IT_API_KEY` is not set, auth is intentionally skipped for local development
- slowapi requires `SlowAPIMiddleware` AND the `_rate_limit_exceeded_handler` registered on the app

### Commits

- `feat: security hardening — auth, rate limiting, prompt separation, env allowlist`
