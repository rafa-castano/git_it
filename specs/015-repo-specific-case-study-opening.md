# Spec 015: Repo-Specific Case Study Opening

Status: Accepted
Owner: AI Development Flow Agent
Primary agent: AI Development Flow Agent
Supporting agents: Software Engineering Agent, Quality Agent
Created: 2026-07-02
Updated: 2026-07-02

## 1. Summary

The opening paragraph of a generated case study's `## Overview` section (the same text the
frontend Overview tab slices out and shows as a short repo intro) must be a brief,
repository-specific introduction — what the analyzed repository appears to be, inferred from
its own commit history and detected patterns — instead of generic boilerplate that could
describe any repository. This spec amends the narrative engine's system prompt (spec 004) and
adds a deterministic post-generation check that flags known generic-opening patterns.

## 2. Problem

`NarrativeService` (spec 004) produces a six-section Markdown case study via an LLM call. The
`## Overview` section's opening sentences currently have no explicit content requirement beyond
"write a structured case study." In practice the LLM sometimes opens with boilerplate such as
"This case study traces what happened in the weeks that followed, using the commit history as
evidence." — a sentence that is true of every repository and conveys nothing about the specific
project.

This matters because `loadOverview()` in `src/git_it/static/app.js` slices the first paragraph
of the `## Overview` section (capped to two sentences) and displays it as the repository's short
description on the Overview tab, before a reader has clicked into the full case study. A generic
opening there wastes the one place in the UI meant to answer "what is this repo?" at a glance.

## 3. Goals

- Instruct the LLM (via the system prompt) to open the `## Overview` section with a brief
  (1–3 sentence), repository-specific introduction inferred strictly from the commit summaries
  and detected patterns already fed into the prompt.
- Explicitly ban the known generic-opening pattern as a negative example in the prompt.
- Add a deterministic, unit-testable guard (`check_opening_quality`) that flags narrative
  openings matching known generic boilerplate phrases, since prompt text alone cannot be
  verified by unit tests.
- Surface (log) a generic-opening detection rather than silently persisting it, per CODEX.md's
  LLM output rules ("do not silently swallow a bad LLM output").
- Apply the same instruction and check to both full generation and incremental regeneration,
  since both produce a complete `## Overview` section.

## 4. Non-goals

- Fetching the repository's GitHub "About" text or description via the GitHub API. That is a
  separate, later enhancement (spec 019) and is explicitly out of scope here — the opening must
  be evidence-grounded in the repository's own commit history, not external metadata.
- Blocking or retrying generation when a generic opening is detected. This spec only requires
  surfacing the problem (logging), not auto-remediation.
- Changing the six-section structure, audience blocks, or synopsis mechanism defined in spec 004.
- Guaranteeing zero false negatives. The banned-phrase list catches known patterns; it is a
  best-effort deterministic guard, not a semantic quality judge.
- Adding a live-LLM eval entry for this behavior in this batch (see Open Questions).

## 5. Users

- Learner: sees a useful, repo-specific one-line description on the Overview tab.
- Developer/operator: sees a WARNING log entry when a generated opening is generic, so prompt
  drift or a weak model choice can be noticed and investigated.

## 6. User stories

```md
As a learner opening a repository's Overview tab,
I want the short intro text to describe what this specific project actually is,
so that I get value from it before deciding whether to read the full case study.
```

```md
As an operator running case-study generation,
I want a log signal when the LLM produces a generic, non-specific opening,
so that I can notice prompt drift or model regressions without reading every narrative.
```

## 7. Acceptance criteria

### AC-01 — System prompt requires a repo-specific opening

```gherkin
Given the narrative engine builds a system prompt (full or incremental generation)
When the prompt is built
Then it contains an explicit instruction that the first paragraph of "## Overview" must be a
  brief, repository-specific introduction inferred from the commit and pattern evidence provided
And it contains the known generic-opening sentence as a banned negative example.
```

### AC-02 — Deterministic opening-quality check flags known generic boilerplate

```gherkin
Given a narrative whose "## Overview" section opens with a known generic phrase
  (e.g. "This case study traces what happened in the weeks that followed, using the commit
  history as evidence.")
When check_opening_quality(narrative) is called
Then the result has is_generic = True and matched_phrase set to the matched banned phrase.
```

```gherkin
Given a narrative whose "## Overview" section opens with repository-specific content
When check_opening_quality(narrative) is called
Then the result has is_generic = False and matched_phrase = None.
```

### AC-03 — Edge cases do not crash the check

```gherkin
Given an empty narrative string
When check_opening_quality(narrative) is called
Then it returns is_generic = False with an empty opening_text, without raising.
```

```gherkin
Given a narrative with no "## " section header at all
When check_opening_quality(narrative) is called
Then the whole narrative is treated as the opening and checked against the banned-phrase list.
```

### AC-04 — Generic opening is logged, not silently persisted

```gherkin
Given NarrativeService.generate() produces (via the LLM) a narrative whose Overview opening
  matches a banned generic phrase
When generation completes (full or incremental path)
Then a WARNING-level log entry is emitted identifying the repository and the matched phrase
And the narrative is still returned and persisted (no hard failure, no retry) — this is a
  visibility signal, not a blocking gate.
```

```gherkin
Given a repository-specific opening
When generation completes
Then no generic-opening warning is logged.
```

## 8. Domain concepts

- **Opening**: the first paragraph of text under the first `## ` section header in a generated
  narrative (normally `## Overview`). Extraction mirrors the existing frontend slicing logic in
  `loadOverview()` (`src/git_it/static/app.js`), reimplemented in Python for testability.
- **Generic boilerplate phrase**: a substring (case-insensitive) known to indicate filler text
  that could describe any repository, drawn from the actual boilerplate observed in this
  project's own narrative outputs plus other common LLM filler patterns.
- **OpeningQualityResult**: the check's return value — `is_generic: bool`,
  `matched_phrase: str | None`, `opening_text: str`. Not a persisted domain entity; it is a
  transient application-layer value used for logging only (see Open Questions for why this is
  not added as a `NarrativeResult` field).

## 9. Inputs and outputs

Inputs:

- The full narrative Markdown string produced by the LLM (after synopsis stripping).

Outputs:

- `OpeningQualityResult(is_generic, matched_phrase, opening_text)` — pure function, no side
  effects.
- A WARNING log record (via `logging.getLogger(__name__)` in `narrative_service.py`) when
  `is_generic` is `True`, emitted by `NarrativeService._log_if_generic_opening()`.

No new fields are added to `NarrativeResult` or `CaseStudyRecord` — the check result is not
persisted (see Open Questions).

## 10. Evidence requirements

The system prompt instruction requires the LLM to ground the opening strictly in the commit
summaries and detected patterns already present in the user message (built by
`_build_user_message` / `_build_incremental_user_message`), consistent with CODEX.md's
"evidence before interpretation" principle. If evidence is too thin to characterize the
repository, the prompt instructs the LLM to say so explicitly rather than inventing details —
this spec does not relax the existing "express uncertainty" and "do not overstate intent"
instructions already present in `_BASE_PROMPT` / `_BASE_INCREMENTAL_PROMPT`.

## 11. Failure modes

| Failure | Behavior |
|---|---|
| LLM still produces a generic opening despite the instruction | Flagged by `check_opening_quality`; a WARNING is logged; narrative is still returned and persisted (no hard failure). |
| Narrative has no `## ` header at all (malformed LLM output) | The whole narrative is treated as the opening; the check still runs without raising. |
| Narrative is empty | `check_opening_quality("")` returns `is_generic=False`, `opening_text=""` — nothing to flag. |
| Banned-phrase list has a false negative (a new, unlisted generic pattern) | Not caught by this deterministic guard. Documented as an accepted limitation (see Open Questions), not a defect this spec fixes. |

## 12. Security considerations

None beyond the existing anti-prompt-injection posture of spec 004 (repository data remains
wrapped in `[REPOSITORY DATA]` tags and treated as untrusted). This spec does not introduce any
new external input path — the banned-phrase list is a fixed, developer-authored constant, and
`check_opening_quality` only inspects LLM output text (already-trusted-boundary output, not raw
repository data).

## 13. Privacy considerations

None. No new data is collected, logged (beyond the opening text itself, which is already part of
the persisted narrative), or transmitted.

## 14. Observability

- New WARNING-level log line in `git_it.repository_ingestion.application.narrative_service`
  when a generic opening is detected, including the repository ID and matched phrase, so
  operators can grep logs for prompt drift.
- No new metrics or persisted fields are added in this batch.

## 15. Tests required

### Unit tests

- `check_opening_quality()`: known-bad generic opening is flagged; known-good repo-specific
  opening passes; empty narrative does not raise; narrative without a `## ` header is still
  checked; only the first paragraph of the Overview section is inspected (a generic phrase in a
  later paragraph must not flag the opening).
- `NarrativeService.generate()` (full-generation path): a generic-opening LLM response causes a
  WARNING log entry; a repo-specific LLM response causes no such log entry.
- `NarrativeService.generate()` (incremental path): the same check runs on incremental
  regeneration output (which also produces a full `## Overview` section).
- System prompt construction: both `_build_system_prompt()` and
  `_build_incremental_system_prompt()` include the new opening-instruction text (verified
  indirectly through `NarrativeService.generate()` in existing test style, matching how spec 004
  tests already assert on system prompt content).

### Evaluation required

Not added in this batch. The existing `evals/` harness (`evals/run.py`,
`evals/golden_commits.json`) is structured specifically around scoring per-commit category and
risk-level classification against hand-labeled commits, and requires a live LLM call gated on an
API key. It is not a fit for narrative-opening quality without a comparable golden-narrative
fixture and scoring rubric, which is a larger undertaking than this batch's scope. Documented as
an assumption in Open Questions; a narrative-quality eval track is a candidate for a future spec.

## 16. Documentation impact

- New prompt-contract doc: `docs/prompt-contracts/narrative-generation.md`, documenting the
  narrative engine's system prompt purpose, inputs, output contract, and this spec's
  anti-generic-opening rule, matching the style of `docs/prompt-contracts/commit-analysis.md`
  and `docs/prompt-contracts/pattern-detection.md`.
- `docs/progress/analysis/batch-88-repo-specific-case-study-opening.md` records this batch's
  work per the repository's commit/documentation discipline.

## 17. ADR impact

None. This is a prompt refinement and an additive deterministic guard within the existing
narrative engine architecture (spec 004); no architectural boundary changes.

## 18. Open questions

- **Why not add `is_generic_opening` as a field on `NarrativeResult` / `CaseStudyRecord`?**
  Assumption made: keep this as a logged signal only, not a persisted field, to avoid growing the
  domain model for a best-effort heuristic that can have false negatives. If operators need this
  queryable/filterable later, promoting it to a persisted field (with its own migration) is a
  follow-up, not part of this batch.
- **Should a detected generic opening trigger an automatic retry?** Assumption made: no. Retrying
  doubles LLM cost for a heuristic that is not proven perfectly accurate, and the rest of the
  narrative may still be valuable even if the opening is weak. Logging preserves visibility
  without forcing a cost/latency tradeoff decision inside this batch.
- **Should the banned-phrase list be configurable/externalized (e.g. a JSON file)?**
  Assumption made: no, keep it a simple in-module constant for now, consistent with other small
  fixed lists in this codebase (e.g. `_AUDIENCE_BLOCKS`). Revisit only if the list grows large
  enough to warrant externalization.
- **Should a narrative-quality eval be added to `evals/`?** Deferred — see "Evaluation required"
  above. Out of scope for this batch; flagged as a candidate follow-up.

## 19. Out of scope

- GitHub API "About" text fetching (spec 019, future).
- Automatic retry or regeneration on detecting a generic opening.
- Streaming narrative output.
- Changes to the six fixed section headers or audience-block mechanism from spec 004.
