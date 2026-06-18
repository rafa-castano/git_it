## Batch 56 — Explicit model allowlist and MCP git permissions fix

### Goal

Two targeted security fixes:
1. Replace the weak `startswith("anthropic/claude-")` prefix check with an explicit allowlist of known models.
2. Restore the agent's ability to `git add` and `git commit` while keeping destructive git operations blocked.

### What was added

**Explicit model allowlist (`schemas.py`):**
- Replaced the `@field_validator` prefix check with a typed `AllowedModel` literal:
  ```python
  AllowedModel = Literal[
      "anthropic/claude-haiku-4-5-20251001",
      "anthropic/claude-sonnet-4-6",
      "anthropic/claude-opus-4-8",
  ]
  ```
- `AnalyzeRequest.model` is now typed `AllowedModel` — Pydantic validates at the schema level, no custom validator needed
- `estimate_analyze` route's `model` query parameter is also typed `AllowedModel`
- Unknown model IDs (e.g. `anthropic/claude-fake`, `openai/gpt-4`) return HTTP 422 automatically
- `field_validator` import removed from `schemas.py` (no longer needed)

**MCP git permissions (`.claude/settings.json`):**
- Removed `mcp__git__git_add` from deny list — agents need this to stage files for batch commits
- Removed `mcp__git__git_commit` from deny list — agents need this to commit batches
- Added `mcp__git__git_push` to deny list — agents must never push to remote
- Remaining denied operations: `git_create_branch`, `git_checkout`, `git_reset`, `git_push`

### Why the allowlist is better than prefix check

`startswith("anthropic/claude-")` allowed any string beginning with that prefix, including non-existent or future models that could fail at the LLM call level with opaque errors. The explicit `Literal` union enumerates only the three tiers the project currently uses; adding a new model requires a deliberate code change.

### Tests

- `test_analyze_rejects_non_anthropic_model` — continues to pass; Pydantic's Literal validation replaces the removed field_validator

### Commits

- `fix: explicit model allowlist and restore git add/commit in MCP permissions`
