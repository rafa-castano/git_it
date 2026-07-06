# Batch 88 — Repo-specific case study opening

## Goal

The frontend Overview tab (`loadOverview()` in `src/git_it/static/app.js`) slices the opening
paragraph of the generated case study's `## Overview` section and displays it as a short repo
description. The narrative engine's system prompt had no explicit requirement for that opening
to be repository-specific, and in practice the LLM sometimes produced generic boilerplate (e.g.
"This case study traces what happened in the weeks that followed, using the commit history as
evidence.") that could describe any repository. Make the opening a brief, repo-specific
introduction inferred from the commit history and detected patterns already fed into the
narrative prompt, and add a deterministic guard to surface (not silently swallow) cases where the
LLM still produces a generic opening.

Locked decision (from the task brief, not reopened): the intro is LLM-inferred from existing
commit/pattern evidence now; no GitHub API "About" text fetch was added (that is spec 019, a
separate future enhancement).

## Source of truth

- `docs/specs/015-repo-specific-case-study-opening.md` (new)
- `docs/specs/004-narrative-engine.md` (existing narrative engine contract, unchanged structurally)
- `docs/prompt-contracts/narrative-generation.md` (new)

## What was added

- `src/git_it/repository_ingestion/application/narrative_service.py`:
  - `_OPENING_INSTRUCTION` — new prompt fragment instructing the LLM that the first paragraph of
    `## Overview` must be a brief, repository-specific introduction inferred from the commit and
    pattern evidence, with the known generic-opening sentence given as a banned negative example.
    Wired into both `_BASE_PROMPT` and `_BASE_INCREMENTAL_PROMPT` via a new `{opening_instruction}`
    format placeholder, injected by `_build_system_prompt()` / `_build_incremental_system_prompt()`.
  - `_GENERIC_OPENING_PHRASES` — a fixed tuple of known generic-boilerplate substrings (built from
    the actual filler observed in this project's narrative outputs, plus other common generic
    opening patterns).
  - `OpeningQualityResult` (frozen dataclass) — `is_generic`, `matched_phrase`, `opening_text`.
    Not persisted; used only for logging.
  - `_extract_overview_opening(narrative)` — reimplements in Python the same slicing logic
    `loadOverview()` uses in JS: first paragraph of the first `## ` section (or the whole
    narrative if there is no `## ` header).
  - `check_opening_quality(narrative)` — pure function; extracts the opening and checks it
    against `_GENERIC_OPENING_PHRASES`.
  - `NarrativeService._log_if_generic_opening(repository_id, narrative)` — static helper called
    from both `_generate_full()` and `_generate_incremental()` right after synopsis extraction;
    logs a WARNING (via `_logger = logging.getLogger(__name__)`) when the opening is flagged.
    Generation still completes and persists normally — this is a visibility signal, not a
    blocking gate or a retry.
- `docs/prompt-contracts/narrative-generation.md` — new prompt-contract doc (purpose, inputs,
  output schema, anti-generic-opening rule, forbidden/failure behavior), matching the style of
  `commit-analysis.md` and `pattern-detection.md`.
- `docs/specs/015-repo-specific-case-study-opening.md` — new spec, Status: Accepted.

## Tests added

- `tests/unit/test_narrative_service.py` (+8 tests):
  - `check_opening_quality` known-bad generic opening → flagged with a matched phrase.
  - `check_opening_quality` known-good repo-specific opening → not flagged.
  - `check_opening_quality` on an empty narrative → not flagged, empty opening text, no raise.
  - `check_opening_quality` on a narrative with no `## ` header at all → still checked (whole
    text treated as the opening).
  - `check_opening_quality` only inspects the first paragraph — a generic phrase in a *later*
    paragraph of `## Overview` must not flag the opening.
  - `NarrativeService.generate()` (full path): a generic-opening LLM response → WARNING logged
    (via `caplog`).
  - `NarrativeService.generate()` (full path): a repo-specific LLM response → no WARNING logged.
  - System prompt (via `generate()`) contains the new repo-specific-opening instruction and the
    banned example phrase.
- `tests/unit/test_case_study_incremental.py` (+1 test):
  - Incremental regeneration (`_generate_incremental`) also runs the check and logs a WARNING for
    a generic opening — confirms the guard is wired into both generation paths, not just the
    full-generation one.

Total: 723 passed / 12 skipped → **732 passed / 12 skipped** (9 new tests, suite stays green).

## Quality gates

- `uv run ruff check .` — all checks passed.
- `uv run ruff format --check .` — 135 files already formatted.
- `uv run mypy src/` — Success: no issues found in 49 source files.
- `uv run pytest -q` — 732 passed, 12 skipped, 1 warning (pre-existing, unrelated).

## Evaluation harness fit

`evals/` (batch 61) is structured specifically for scoring per-commit `category`/`risk_level`
classification against hand-labeled golden commits, and requires a live LLM call gated behind an
API key. It does not fit narrative-opening quality without a comparable golden-narrative fixture
and scoring rubric — building that is a larger undertaking than this batch's scope. No eval entry
was added; documented as an open question in the spec for a possible future narrative-quality
eval track.

## Gotchas

- The frontend (`app.js` `loadOverview()`) and the new Python `_extract_overview_opening()`
  implement the *same* slicing algorithm in two languages (JS reads the live narrative for
  display; Python checks the freshly generated narrative before it's ever displayed). They must
  stay in sync — if the frontend slicing logic changes, the Python mirror needs the matching
  update, or the deterministic check will validate a different paragraph than what users actually
  see. Documented in code comments on both sides.
- The banned-phrase list is a best-effort deterministic guard, not a semantic quality judge — it
  only catches the specific patterns it knows about. A new, unlisted generic phrasing from the
  LLM would pass through undetected. This is called out explicitly in the spec's Open Questions
  rather than treated as a defect.
- Chose logging (WARNING) over blocking/retrying generation when a generic opening is detected,
  to avoid doubling LLM cost on a heuristic that isn't proven perfectly accurate — the rest of
  the narrative may still be valuable even when the opening is weak.
- No new persisted field was added to `NarrativeResult` / `CaseStudyRecord` for this signal
  (deliberately, per the spec's Open Questions) — it's a logged signal only, keeping the domain
  model unchanged for a best-effort heuristic.

## Commits

- `feat: require repo-specific case study openings and flag generic ones` — (this commit; see
  `git log -1 --format=%H` for the exact SHA, recorded in the next batch's progress doc per this
  repo's usual practice of confirming a commit's own SHA after the fact).
