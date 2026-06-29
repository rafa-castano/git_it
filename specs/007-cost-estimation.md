# Spec 007: Cost Estimation

Status: Accepted
Owner: Software Engineering Agent
Primary agent: Software Engineering Agent
Supporting agents: AI Development Flow Agent, Quality Agent
Created: 2026-06-29
Updated: 2026-06-29

## 1. Summary

A read-only endpoint that estimates the dollar cost of running commit analysis and narrative
generation for a repository before the user triggers the actual analysis. The estimate breaks
the total cost into two independent components—analysis cost and narrative cost—and returns both
components alongside the total.

## 2. Problem

LLM calls are not free. Without a cost estimate, users have no way to anticipate the financial
impact of analyzing a large repository. The endpoint lets users make an informed decision before
committing to a potentially expensive operation.

## 3. Goals

- Return a cost estimate before any LLM call is made.
- Break the estimate into analysis cost (Haiku, per-commit) and narrative cost (Sonnet, based on
  total commit count).
- Return `estimated_narrative_cost_usd` even when `estimated_llm_calls == 0`, because the
  narrative can be regenerated independently of new commit analysis.
- Round monetary values consistently to four decimal places.

## 4. Non-goals

- Actual billing or payment processing.
- Per-user cost tracking or budgets.
- Estimates for endpoints other than the analyze flow.
- Caching or persisting cost estimates.

## 5. Users

- Developer: calls the endpoint before triggering analysis to decide whether to proceed.
- Frontend: displays the cost breakdown in the UI before the user confirms analysis.

## 6. User stories

```md
As a developer,
I want to see an estimated cost before analyzing a repository,
so that I can decide whether to proceed without surprises on my LLM bill.
```

```md
As a frontend,
I want both cost components (analysis + narrative) separately,
so that I can display a breakdown rather than a single opaque total.
```

## 7. Acceptance criteria

### AC-01 — Response shape

```gherkin
Given a valid repository_id with ingested commits
When GET /api/repos/{repository_id}/analyze/estimate is called
Then the response contains all seven fields:
  total_commits (int)
  analyzed_commits (int)
  unanalyzed_commits (int)
  estimated_llm_calls (int)
  estimated_analysis_cost_usd (float)
  estimated_narrative_cost_usd (float)
  estimated_cost_usd (float)
```

### AC-02 — Total equals sum of components

```gherkin
Given any repository with total_commits > 0
When GET /api/repos/{repository_id}/analyze/estimate is called
Then estimated_cost_usd == round(estimated_analysis_cost_usd + estimated_narrative_cost_usd, 4).
```

### AC-03 — Narrative cost is zero when total_commits is zero

```gherkin
Given a repository with total_commits == 0
When GET /api/repos/{repository_id}/analyze/estimate is called
Then estimated_narrative_cost_usd == 0.0
And estimated_cost_usd == estimated_analysis_cost_usd.
```

### AC-04 — Narrative cost scales with total commit count

```gherkin
Given repository A with N commits and repository B with 2N commits
When GET /api/repos/{id}/analyze/estimate is called for each
Then B's estimated_narrative_cost_usd is greater than A's estimated_narrative_cost_usd.
```

```gherkin
Given a repository with 100 total_commits
When GET /api/repos/{repository_id}/analyze/estimate is called
Then estimated_narrative_cost_usd equals round(
  (500 + 100 * 45) * (3.0 / 1_000_000) + 4000 * (15.0 / 1_000_000),
  4
).
```

### AC-05 — Narrative cost returned even when estimated_llm_calls is zero

```gherkin
Given a repository where all commits have already been analyzed (estimated_llm_calls == 0)
And total_commits > 0
When GET /api/repos/{repository_id}/analyze/estimate is called
Then estimated_narrative_cost_usd > 0.0
And estimated_cost_usd == estimated_narrative_cost_usd.
```

_Rationale_: `estimated_narrative_cost_usd` is based on `total_commits` (the full repository
history), not on `estimated_llm_calls`. Even when no new commit analysis would run, the user
may choose to regenerate the narrative independently, so the cost is always surfaced.

### AC-06 — Analysis cost scales with estimated LLM calls

```gherkin
Given estimated_llm_calls == K (K > 0)
When GET /api/repos/{repository_id}/analyze/estimate is called
Then estimated_analysis_cost_usd == round(K * 0.0008, 4).
```

### AC-07 — unanalyzed_commits is bounded below by zero

```gherkin
Given analyzed_commits >= total_commits
When GET /api/repos/{repository_id}/analyze/estimate is called
Then unanalyzed_commits == 0.
```

### AC-08 — Repository not found

```gherkin
Given a repository_id for which no database file exists
When GET /api/repos/{repository_id}/analyze/estimate is called
Then the response status is 404.
```

## 8. Inputs

| Parameter | Type | Location | Default | Description |
|---|---|---|---|---|
| `repository_id` | str | path | required | Identifies the repository. |
| `limit` | int | query | 20 | Maximum number of new commits to analyze (used for LLM call estimation). |
| `model` | str | query | `anthropic/claude-haiku-4-5-20251001` | Model name passed to the analysis service for call estimation. |

## 9. Outputs

`AnalyzeEstimateResponse` (JSON):

| Field | Type | Description |
|---|---|---|
| `total_commits` | int | Total commits ingested for the repository. |
| `analyzed_commits` | int | Commits that already have an analysis result. |
| `unanalyzed_commits` | int | `max(0, total_commits - analyzed_commits)`. |
| `estimated_llm_calls` | int | Number of Haiku LLM calls that would be made for new commit analysis. |
| `estimated_analysis_cost_usd` | float | `round(estimated_llm_calls * per_call_cost, 4)`. |
| `estimated_narrative_cost_usd` | float | Cost of one Sonnet narrative generation call; 0.0 when `total_commits == 0`. |
| `estimated_cost_usd` | float | `round(estimated_analysis_cost_usd + estimated_narrative_cost_usd, 4)`. |

## 10. Domain model impact

None. The endpoint is read-only and does not modify any stored state.

## 11. API impact

```
GET /api/repos/{repository_id}/analyze/estimate
```

- No authentication required (read-only estimate).
- Query parameters: `limit` (int, default 20), `model` (str, default Haiku model string).
- Returns 404 if the SQLite database file does not exist.

## 12. Data model impact

None. The endpoint reads from existing commit and analysis count tables but writes nothing.

## 13. Cost model

### Analysis cost

```
estimated_analysis_cost_usd = round(estimated_llm_calls * PER_CALL_COST, 4)
```

Where:
- `estimated_llm_calls` is determined by `CommitAnalysisService.estimate_llm_calls()`.
- `PER_CALL_COST` is the approximate cost of one Haiku analysis call (currently `$0.0008`).

### Narrative cost

```
narrative_cost(total_commits):
  if total_commits == 0:
    return 0.0
  input_tokens  = NARRATIVE_BASE_INPUT_TOKENS + total_commits * NARRATIVE_TOKENS_PER_COMMIT
  output_tokens = NARRATIVE_OUTPUT_TOKENS
  return round(
    input_tokens  * SONNET_INPUT_COST_PER_TOKEN
    + output_tokens * SONNET_OUTPUT_COST_PER_TOKEN,
    4
  )
```

Current constant values (may be centralized in a later batch — reference: constants centralized
in batch 74; the spec describes the model, not where the constants live):

| Constant | Value | Unit |
|---|---|---|
| `NARRATIVE_BASE_INPUT_TOKENS` | 500 | tokens (system prompt) |
| `NARRATIVE_TOKENS_PER_COMMIT` | 45 | tokens per commit in the user message |
| `NARRATIVE_OUTPUT_TOKENS` | 4 000 | tokens (conservative average output) |
| `SONNET_INPUT_COST_PER_TOKEN` | 3.0 / 1 000 000 | USD per token |
| `SONNET_OUTPUT_COST_PER_TOKEN` | 15.0 / 1 000 000 | USD per token |

Model: `claude-sonnet-4-6` (used for narrative generation).

### Narrative cost independence from analysis calls

`estimated_narrative_cost_usd` is computed from `total_commits`, not from
`estimated_llm_calls`. This is intentional: the narrative generation call processes the full
commit history regardless of how many new commits triggered the update. Even when
`estimated_llm_calls == 0` (all commits already analyzed), the user may independently trigger
narrative regeneration, so the cost is always included in the estimate.

### Total cost

```
estimated_cost_usd = round(estimated_analysis_cost_usd + estimated_narrative_cost_usd, 4)
```

## 14. Evidence requirements

The cost estimate is a deterministic calculation from stored counts and known constants. No
LLM-generated claims are made. No evidence linking is required.

## 15. Security considerations

- The endpoint is read-only and returns no sensitive repository data.
- No API key is required (consistent with other read-only repository endpoints).
- `repository_id` is validated implicitly by checking for the existence of the SQLite database
  file; no path traversal is possible because the database path is derived server-side.

## 16. Privacy considerations

No personal data is returned. Commit counts are aggregate statistics.

## 17. Observability

- 404 responses are logged when the database file is not found.
- No additional metrics are required for a read-only estimation endpoint.

## 18. Test strategy

### Unit tests

- `_estimate_narrative_cost(0)` returns `0.0`.
- `_estimate_narrative_cost(N)` returns the expected rounded value for representative N.
- `estimate_analyze` endpoint returns 404 when the database file does not exist.
- `estimated_cost_usd` equals `round(analysis + narrative, 4)` for multiple inputs.

### Integration tests

- Call `GET /analyze/estimate` against a seeded test database with known commit and analysis
  counts; assert all seven response fields match expected values.
- When `estimated_llm_calls == 0` and `total_commits > 0`, assert `estimated_narrative_cost_usd
  > 0`.

### E2E tests

- Not required for a read-only calculation endpoint.

## 19. ADR impact

None.

## 20. Open questions

- Should the narrative cost estimate account for the synopsis optimization (incremental updates
  use fewer tokens)? Currently it assumes a full generation for conservatism.
- Should the per-call cost and narrative cost constants be surfaced in the response so clients
  can display model-specific breakdowns?

## 21. Out of scope

- Real-time cost tracking against actual API usage.
- Per-model cost breakdowns in the response.
- Estimates for pattern detection or ingestion steps.
