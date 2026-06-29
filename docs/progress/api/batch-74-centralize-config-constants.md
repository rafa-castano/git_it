# Batch 74 — Centralize model, cost, and audience constants

## Goal

Eliminate duplicated configuration spread across five files. An audit identified three
categories of duplication:

1. Model name `"anthropic/claude-haiku-4-5-20251001"` defined in `infrastructure/llm.py`
   (canonical) but repeated as raw literals in `interfaces/cli.py`, `api/routes/repos.py`,
   and `api/schemas.py`.
2. Cost constants (`_LLM_COST_PER_CALL_USD` and the six Sonnet narrative constants) and
   `_estimate_narrative_cost()` living only in `api/routes/repos.py`, plus the magic number
   `0.0008` hardcoded again in `static/index.html`.
3. Audience default `"beginner"` scattered across `routes/repos.py`, `narrative_service.py`,
   `schemas.py`, and `ports.py` as independent literals.

This batch is a pure refactor-under-green: no behavior changes, tests must stay green.

## Canonical-location decision

### Model name (`DEFAULT_MODEL`)

Kept in `src/git_it/repository_ingestion/infrastructure/llm.py` — it was already the
authoritative source for the adapters. The name changed from private `_DEFAULT_MODEL` to
public `DEFAULT_MODEL` (with `_DEFAULT_MODEL = DEFAULT_MODEL` kept as a module-internal alias
so the adapter defaults remain unchanged). All other sites import this constant rather than
repeating the literal.

The `cli.py` help-text string (`"e.g. anthropic/claude-haiku-4-5-20251001"`) is intentional
prose for the user-facing CLI help output, not a configuration point, so it was left as-is.

### Cost model (`src/git_it/api/cost.py`)

A new thin module was created for the pricing constants and `estimate_narrative_cost()`. The
cost model is an API-layer concern: it translates LLM call counts into USD estimates for the
`/analyze/estimate` endpoint. It does not belong in the domain or application layers, and
putting it in `api/routes/repos.py` made the module do two unrelated things (HTTP routing +
pricing). The dedicated module also makes future pricing updates trivial to find.

`routes/repos.py` now imports `LLM_COST_PER_CALL_USD` and `estimate_narrative_cost` from
`api/cost.py`, with no behavior change.

### Audience default (`DEFAULT_AUDIENCE`)

Added `DEFAULT_AUDIENCE = "beginner"` to
`src/git_it/repository_ingestion/application/ports.py` and included it in `__all__`. This is
the correct hexagonal home: `ports.py` already defines `CaseStudyRecord` (which carries an
`audience` field) and the `CaseStudyStore` protocol (which has an `audience` parameter). The
application and API layers both legitimately import from ports, so there are no import cycles.

SQL DDL default strings in `sqlite.py` and `postgres.py` were intentionally left unchanged —
they are database schema declarations, not application configuration points.

Frontend JS fallbacks in `index.html` for localStorage (e.g. `|| 'beginner'`) were also left
unchanged — they are UI state initializations driven by the browser, not Python constants.

## Changes Made

### `src/git_it/repository_ingestion/infrastructure/llm.py`
- Added `DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"` as a public constant.
- Changed `_DEFAULT_MODEL` to `_DEFAULT_MODEL = DEFAULT_MODEL` (module-internal alias).

### `src/git_it/repository_ingestion/application/ports.py`
- Added `DEFAULT_AUDIENCE = "beginner"` at module level (before `__all__`).
- Added `"DEFAULT_AUDIENCE"` to `__all__`.
- Changed `CaseStudyRecord.audience` field default to use `DEFAULT_AUDIENCE`.
- Changed `CaseStudyStore.get_case_study` parameter default to use `DEFAULT_AUDIENCE`.

### `src/git_it/api/cost.py` (new)
- `LLM_COST_PER_CALL_USD = 0.0008` — haiku analysis cost per call.
- Six Sonnet narrative cost constants.
- `estimate_narrative_cost(total_commits: int) -> float` — same logic, moved here.

### `src/git_it/api/routes/repos.py`
- Removed the six cost constants and `_estimate_narrative_cost()`.
- Added imports: `LLM_COST_PER_CALL_USD`, `estimate_narrative_cost` from `api/cost`;
  `DEFAULT_AUDIENCE` from `ports`; `DEFAULT_MODEL` from `infrastructure/llm`.
- Replaced all three hardcoded `"anthropic/claude-haiku-4-5-20251001"` occurrences with
  `DEFAULT_MODEL`.
- Replaced all `audience: str = "beginner"` function parameter defaults and the dict literal
  default `{"running": False, "audience": "beginner"}` with `DEFAULT_AUDIENCE`.

### `src/git_it/api/schemas.py`
- Added imports of `DEFAULT_AUDIENCE` and `DEFAULT_MODEL`.
- `AnalyzeRequest.model`, `AnalyzeRequest.audience`, `RegenerateRequest.audience` now use the
  constants instead of string literals.

### `src/git_it/repository_ingestion/interfaces/cli.py`
- Removed local `_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"`.
- Added `from git_it.repository_ingestion.infrastructure.llm import DEFAULT_MODEL as _DEFAULT_MODEL`
  so the rest of the module requires no further changes.

### `src/git_it/repository_ingestion/application/narrative_service.py`
- Added `DEFAULT_AUDIENCE` to the `ports` import.
- Changed all three `audience: str = "beginner"` method parameter defaults to use
  `DEFAULT_AUDIENCE`.

### `src/git_it/static/index.html`
- Line ~2174: replaced `… : 0.0008` with `… : 0`.
  The fallback triggers only when `estimated_llm_calls` is 0, in which case the scaled cost
  is already 0 (0 calls × anything = 0). The old fallback was both wrong (0 calls should cost
  $0, not $0.0008) and a hardcoded price constant in JS. The API always returns
  `estimated_analysis_cost_usd`, so the computed path is always taken when calls > 0.

## Files Changed

- `src/git_it/repository_ingestion/infrastructure/llm.py` — public `DEFAULT_MODEL` constant
- `src/git_it/repository_ingestion/application/ports.py` — `DEFAULT_AUDIENCE` constant
- `src/git_it/api/cost.py` — new: canonical cost constants + `estimate_narrative_cost()`
- `src/git_it/api/routes/repos.py` — imports, remove duplicates
- `src/git_it/api/schemas.py` — imports, use constants for field defaults
- `src/git_it/repository_ingestion/interfaces/cli.py` — import `DEFAULT_MODEL`, remove local copy
- `src/git_it/repository_ingestion/application/narrative_service.py` — use `DEFAULT_AUDIENCE`
- `src/git_it/static/index.html` — remove `0.0008` magic number
- `docs/progress/api/batch-74-centralize-config-constants.md` — this document
- `docs/progress/README.md` — index entry

## Tests Added

No new tests added. The existing estimate cost tests in `tests/unit/test_api_analyze.py`
(`test_estimate_narrative_cost_scales_with_commits`,
`test_estimate_narrative_cost_zero_when_no_commits`, and the analysis cost assertion in
`test_estimate_returns_cost_fields`) serve as the equivalence proof — they pass against the
moved code with identical results.

Full unit suite after all changes: **576 passed, 8 skipped**.

## Gotchas

- `ruff` reordered the new imports in `routes/repos.py` (isort I001). Fixed with
  `ruff check --fix` before committing — pre-commit hook would have caught it otherwise.
- SQL DDL strings in `sqlite.py`/`postgres.py` contain `'beginner'` as database schema
  defaults. These are SQL string literals inside Python strings and must NOT be replaced with
  Python constants — the SQL is passed to the database engine, not Python.
- The `cli.py` help text `"e.g. anthropic/claude-haiku-4-5-20251001"` is documentation, not
  a configuration default; it was left as a string literal intentionally.
- mypy reports one pre-existing `psycopg2` missing-stub error in `postgres.py`. This batch
  introduces zero new mypy errors.
