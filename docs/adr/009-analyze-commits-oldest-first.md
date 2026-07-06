# ADR 009: Process Not-Yet-Analyzed Commits Oldest-First

Status: Accepted  
Date: 2026-06-29  
Decision makers: Architecture Agent

## Context

The commit-analysis background job (`_analyze_bg` in `src/git_it/api/routes/repos.py`) calls
`CommitAnalysisService.analyze_commits` to send unanalyzed commits to the LLM one at a time.
The order in which commits are fed to the LLM matters because subsequent case-study generation
(`NarrativeService.generate`) builds a chronological engineering story from the accumulated
analyses.

Before the fix documented in
`docs/progress/api/bugfix-session-ui-and-ordering.md` (Fix 1, commit `539bb30`),
`_analyze_bg` passed `order="newest"` to `analyze_commits`. This caused commits to be analyzed
in reverse chronological order, which meant the first analyses stored in the database represented
recent changes. When the incremental case-study incorporated new commits it lacked the
foundational historical context that the chronological narrative depends on — the story started
in the middle rather than at the beginning.

## Decision

The background analysis job processes not-yet-analyzed commits in ascending chronological order
(oldest commit first).

Code evidence — `src/git_it/api/routes/repos.py`, function `_analyze_bg`:

```python
svc.analyze_commits(
    repository_id,
    limit=None,
    max_new=limit,
    order="oldest",          # <-- the decision
    on_progress=_on_progress,
    canonical_url=canonical_url,
)
```

### Minor inconsistency — estimate endpoint

`estimate_analyze` (same file) calls `svc.estimate_llm_calls(repository_id, limit=limit, order="newest")`.
The estimate endpoint uses `order="newest"` to count how many of the *most-recent* commits
still need analysis — a common UI use case where users want to know the cost of analyzing the
latest work first. This ordering difference does NOT affect the estimated cost total; it only
determines which `limit` commits are counted. The estimate is intentionally pessimistic (picks
from the newest end) while actual analysis is processed oldest-first. This discrepancy is
acknowledged as a known, acceptable asymmetry for the MVP.

## Consequences

### Positive

- The case-study narrative receives historical context in chronological order, producing a
  coherent engineering story that starts at the project's beginning.
- Incremental updates (new commits analyzed after the first generation) extend the story
  forward in time rather than inserting context out of sequence.
- Matches how learners read a project's history: from founding decision to present state.

### Negative

- If a user's primary interest is the most-recent commits, they must wait for older commits
  to be analyzed first before reaching the ones they care about.
- The estimate endpoint uses a different ordering assumption, which may surprise contributors
  reading the code.

### Neutral

- The `order` parameter is already passed through `CommitAnalysisService.analyze_commits`,
  so no new abstraction was needed — one argument value change was sufficient.
- The inconsistency between `_analyze_bg` (`"oldest"`) and `estimate_analyze` (`"newest"`)
  is documented here and does not need to be resolved for the MVP.

## Alternatives considered

**Newest-first analysis:** Prioritizes recent commits and lets users see analysis of current
work sooner. Trade-off: the case-study narrative loses historical coherence because the LLM
receives context in reverse order. The incremental synopsis cannot accurately summarise the
project arc when foundational commits have not yet been analyzed.

**User-selectable order:** Expose an `order` parameter in the analyze API. Trade-off: adds
API surface and UX complexity with limited benefit for the MVP single-process workflow. Deferred
until a concrete user need justifies it.

## Security impact

No security impact. The change only affects the SQL query order used to fetch unanalyzed
commits — it does not alter data written to the database, change trust boundaries, or affect
prompt-injection mitigations.

## Quality impact

Test `tests/unit/test_commit_analysis_ordering.py` covers the `order` parameter contract for
`CommitAnalysisService.analyze_commits`. The background-job integration is validated indirectly
via `tests/unit/test_api_analyze.py`.

## Documentation impact

- `docs/progress/api/bugfix-session-ui-and-ordering.md` — records the original bug and the
  one-line fix that established this decision.
- `docs/specs/004-narrative-engine.md` — the narrative engine spec documents how case studies are
  built from ordered analyses.

## Links

- `docs/specs/004-narrative-engine.md`
- `docs/progress/api/bugfix-session-ui-and-ordering.md`
- `src/git_it/api/routes/repos.py` — `_analyze_bg` (production decision) and `estimate_analyze`
  (acknowledged inconsistency)
