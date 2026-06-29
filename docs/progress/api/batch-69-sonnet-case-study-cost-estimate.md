# Batch 69 — Sonnet case study cost in analyze estimate

## Goal

The analyze estimate previously accounted only for Haiku commit-analysis calls. This batch adds
the Sonnet case study generation cost so the confirm dialog shows the real total, broken down into
analysis cost and narrative cost.

Commit: `ccd64532838d64c53f8603998b5bbd7bfaf527e1`

## Changes Made

### New schema fields

`src/git_it/api/schemas.py`

Two new fields added to `AnalyzeEstimateResponse`:
- `estimated_analysis_cost_usd: float` — Haiku commit-analysis calls only
- `estimated_narrative_cost_usd: float` — Sonnet case study generation

The existing `estimated_cost_usd` field is now the sum of both components (previously it equalled
`estimated_analysis_cost_usd` alone).

### `_estimate_narrative_cost()` — Sonnet pricing model

`src/git_it/api/routes/repos.py`

New module-level constants and helper:

```python
_SONNET_INPUT_COST_PER_TOKEN  = 3.0  / 1_000_000   # $3  / MTok
_SONNET_OUTPUT_COST_PER_TOKEN = 15.0 / 1_000_000   # $15 / MTok
_NARRATIVE_BASE_INPUT_TOKENS  = 500                 # system prompt
_NARRATIVE_TOKENS_PER_COMMIT  = 45                  # per-commit tokens in user message
_NARRATIVE_OUTPUT_TOKENS      = 4000                # conservative average output
```

`_estimate_narrative_cost(total_commits: int) -> float`:
- Returns `0.0` immediately when `total_commits == 0` (no case study generated for empty repos).
- Otherwise computes `input_tokens = 500 + total_commits * 45`, then
  `input_tokens * $3/MTok + 4000 * $15/MTok`, rounded to 4 decimal places.

### `estimate_analyze` endpoint update

`src/git_it/api/routes/repos.py` — `estimate_analyze`

The endpoint now computes:
```python
estimated_analysis_cost = round(estimated_llm_calls * _LLM_COST_PER_CALL_USD, 4)
estimated_narrative_cost = _estimate_narrative_cost(total_commits)
```

and returns all three fields in the response (`estimated_analysis_cost_usd`,
`estimated_narrative_cost_usd`, `estimated_cost_usd = analysis + narrative`).

### Frontend confirm dialog

`src/git_it/static/index.html` — `_doAnalyze`

Two lines changed:
- `costPerCall` now divides `estimated_analysis_cost_usd` (not the total) by
  `estimated_llm_calls`, so the per-call scaling factor is based solely on the analysis portion.
- `scaledCost = scaledCalls * costPerCall + (est.estimated_narrative_cost_usd || 0)` — narrative
  cost is added as a fixed amount (it does not scale with the limit, since one case study is
  generated regardless of the commit slice).

## Files Changed

- `src/git_it/api/schemas.py` — two new fields on `AnalyzeEstimateResponse`
- `src/git_it/api/routes/repos.py` — `_estimate_narrative_cost`, updated `estimate_analyze`
- `src/git_it/static/index.html` — confirm dialog cost calculation
- `tests/unit/test_api_analyze.py` — updated existing test + 2 new tests

## Tests Added

**`test_estimate_cost_proportional_to_llm_calls`** (updated): now asserts all three cost fields
and verifies `estimated_cost_usd == estimated_analysis_cost_usd + estimated_narrative_cost_usd`.

**`test_estimate_narrative_cost_scales_with_commits`** (new): creates two databases with 1 and 20
commits respectively; asserts that the 20-commit repo returns a higher `estimated_narrative_cost_usd`.

**`test_estimate_narrative_cost_zero_when_no_commits`** (new): empty database returns
`estimated_narrative_cost_usd == 0.0`.

## Gotchas

- The narrative cost is a fixed fee per analysis run — it does not scale with the `limit` parameter
  because one case study generation covers all commits. The frontend adds it as a constant on top
  of the scaled analysis cost.
- The output token estimate (4000) is conservative. Real Sonnet outputs for a full case study are
  typically longer; this keeps the displayed estimate on the low side to avoid alarming users.
- `estimated_narrative_cost_usd` is returned even when `estimated_llm_calls == 0` (all commits
  already analyzed), since a case study regeneration still incurs the narrative cost.
