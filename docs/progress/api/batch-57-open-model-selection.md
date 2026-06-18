## Batch 57 — Open model selection (any LiteLLM provider)

### Goal

Remove the Anthropic-only model restriction so users can pass any LiteLLM-compatible model string — matching the UX of tools like OpenCode that support any provider.

### What changed

- Removed `AllowedModel = Literal[...]` from `schemas.py`
- `AnalyzeRequest.model` is now `str` (default unchanged: `anthropic/claude-haiku-4-5-20251001`)
- `estimate_analyze` route `model` query param is now `str`
- Removed `AllowedModel` import from `routes/repos.py`

Any model string supported by LiteLLM now works: `openai/gpt-4o`, `gemini/gemini-2.0-flash`, `anthropic/claude-sonnet-4-6`, etc.

### Tests updated

- `test_analyze_rejects_non_anthropic_model` → `test_analyze_accepts_any_litellm_model`
  Confirms that `openai/gpt-4o` returns 200 (background thread is kicked off), not 422

### Commits

- `feat: allow any LiteLLM-compatible model in analyze and estimate endpoints`
