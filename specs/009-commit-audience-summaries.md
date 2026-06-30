# Feature Spec: 009 — Dual-Audience Commit Summaries

## Summary

Extend the commit analysis pipeline so that each analyzed commit carries two
audience-aware summaries: one for beginners and one for experienced engineers.
The LLM produces both summaries in a single call.  When a commit message is
already self-explanatory for a given audience the LLM emits an empty summary for
that audience, which suppresses the expand arrow on the frontend. A toggle on the
Commits tab lets users switch audiences instantly without re-fetching.

---

## Problem

The current `CommitAnalysis.summary` field is audience-agnostic.  Beginners are
overwhelmed by technical jargon; experienced engineers find simplified language
condescending.  There is no way to adapt the explanation to the reader without a
separate LLM call per audience.  Additionally, the system always renders an expand
row even when the summary is a near-verbatim copy of the commit message, adding
visual noise with no informational value.

---

## Goals

1. Produce `summary_beginner` and `summary_expert` in a single LLM call per commit.
2. Return empty string `""` for an audience's summary when the commit message is
   self-explanatory for that audience (drives "no expand arrow" on the frontend).
3. Surface both fields via the `/commits` API endpoint.
4. Add a Beginner / Expert toggle to the Commits tab; the selected audience is
   persisted in `localStorage` under key `commit-audience`.
5. Existing analyzed commits (with `summary_beginner = None`) are re-analyzed
   transparently on the next `git-it analyze` run without requiring a `--force` flag.

---

## Non-goals

- Removing the legacy `summary` field from the schema or the DB (back-compat retained).
- Per-audience filtering of the commit list (only the expand-row text changes).
- Separate LLM calls for each audience (both must come from one call).
- Audience-aware case study summaries (spec 004 already handles narrative audience).

---

## Users

- **Students / learners**: want plain-language explanations of commits without jargon.
- **Professional engineers**: want terse, technically precise context.

---

## User stories

1. As a student, when I open the Commits tab I see commit explanations in plain
   language.  I can switch to Expert mode to see the technical version.
2. As an engineer, the default Expert mode shows precise, jargon-rich summaries.
   When a commit message already tells the full story, no expand row is shown.
3. As a user re-running analysis on an already-analyzed repo, existing commits that
   pre-date this feature are automatically upgraded on the next analyze run.

---

## Acceptance criteria

### AC-1 — Domain schema
- `CommitAnalysis` gains two optional fields:
  `summary_beginner: str | None = None` and `summary_expert: str | None = None`.
- `summary: str` remains a required field (back-compat).
- Pydantic serialization round-trips correctly for both old JSON (missing new fields
  → `None`) and new JSON (all three fields present).

### AC-2 — LLM prompt
- The system prompt instructs the LLM to produce BOTH `summary_beginner` and
  `summary_expert` in the same JSON response.
- For each field: if the commit message already fully captures the meaning for that
  audience, the LLM MUST return `""` (empty string).
- `summary_beginner` targets readers with < 1 year of experience; no jargon,
  analogies welcome, ≤ 2 sentences.
- `summary_expert` targets senior engineers; terse, precise, technical, ≤ 1 sentence.
- The existing `summary` field continues to be populated (set equal to
  `summary_expert` or a reasonable default) for back-compat.

### AC-3 — Re-analysis trigger
- `CommitAnalysisService.analyze_commits()` skips cached analyses ONLY when
  `cached.summary_beginner is not None`.
- Commits cached before this feature (where `summary_beginner is None`) are
  treated as needing re-analysis.
- `estimate_analysis_calls()` uses the same condition so the cost estimate matches.

### AC-4 — API
- `CommitSummaryItem` in `schemas.py` gains:
  `summary_beginner: str | None = None` and `summary_expert: str | None = None`.
- `GET /api/repos/{id}/commits` returns both fields for every commit that has been
  analyzed with the new schema; `None` for commits analyzed before this feature.

### AC-5 — Persistence
- No DB migration needed: `summary_beginner` and `summary_expert` are stored inside
  the existing `commit_analyses.data` JSON blob.
- `SqliteCommitAnalysisAdapter.save_analysis()` already serializes the full model.
- `get_analysis()` already uses `model_validate_json()` which applies Pydantic
  defaults, so old rows get `summary_beginner = None` automatically.

### AC-6 — Frontend toggle
- The Commits tab filter bar gains a Beginner / Expert `<select>` (id:
  `commit-audience-select`) defaulting to `"expert"`.
- Selection is persisted in `localStorage['commit-audience']` and restored on load.
- When the selected audience changes, the timeline re-renders using
  `_applyTimelineFilters()` (no network call).
- For each commit row:
  - If `summary_beginner is not None` (new schema): use `summary_beginner` or
    `summary_expert` depending on the selected audience.
  - If both new fields are `None` (legacy): fall back to `summary`.
- The expand arrow and expand-detail text reflect the active audience's summary.

### AC-7 — Empty summary → no expand arrow
- When the active audience's resolved summary is `""` (empty string), no expand
  arrow is rendered and the row is not interactive (`role` attribute absent).
- When the active audience's resolved summary equals the commit message verbatim,
  the same applies (no arrow).

---

## Domain concepts

| Concept | Definition |
|---|---|
| `summary_beginner` | LLM-produced plain-language explanation for < 1 year experience readers; `""` when the message is self-explanatory; `None` for pre-feature analyses |
| `summary_expert` | LLM-produced terse technical explanation for senior engineers; same sentinel values |
| Active audience | The audience currently selected in the Commits tab; persisted in `localStorage` |
| Re-analysis trigger | `summary_beginner is None` on a cached analysis indicates the commit was analyzed before this feature and needs re-analysis |

---

## Inputs and outputs

### Inputs
- Existing `CommitRecord` (sha, message, committed_at, author_name) — unchanged.
- `_SYSTEM_PROMPT` extended with dual-audience instructions.

### LLM output JSON schema (new fields only)
```json
{
  "summary_beginner": "...",
  "summary_expert": "...",
  "summary": "..."
}
```

### API output addition to `CommitSummaryItem`
```json
{
  "summary_beginner": "Explanation for beginners, or empty string, or null",
  "summary_expert": "Terse technical note, or empty string, or null"
}
```

---

## Evidence requirements

- The `summary_beginner` and `summary_expert` fields must come from the LLM
  response, not post-processed from `summary`.
- An empty string in `summary_beginner` must be stored as `""`, not `None`.
- Evidence of AC-3: unit test must show that a `CommitAnalysis` with
  `summary_beginner=None` is re-analyzed; one with `summary_beginner=""` is skipped.

---

## Failure modes

| Mode | Behaviour |
|---|---|
| LLM returns old schema without new fields | Pydantic defaults apply: `summary_beginner = None`, `summary_expert = None`; back-compat preserved |
| LLM returns non-empty `summary_beginner` for trivial commit | Not a hard failure; arrows appear but text may be redundant. No special handling needed |
| `localStorage` unavailable (e.g. private browsing) | Fall back to default `"expert"`; no error surfaced to user |

---

## Security considerations

- No new untrusted input surfaces; commit data is already treated as untrusted.
- `summary_beginner` and `summary_expert` must be HTML-escaped before rendering
  (same as the existing `summary` field via `esc()`).

---

## Privacy considerations

- No change to what is sent to the LLM; same commit fields as before.

---

## Observability

- Debug log at the LLM adapter level already logs model/sha/duration.
- No additional metrics needed for this feature.

---

## Tests required

| Test | Location |
|---|---|
| `CommitAnalysis` accepts old JSON without new fields → defaults to `None` | `tests/unit/test_domain_analysis.py` |
| `CommitAnalysis` round-trips with all three summary fields | `tests/unit/test_domain_analysis.py` |
| `summary_beginner = None` → re-analyze; `summary_beginner = ""` → skip | `tests/unit/test_commit_analysis_service.py` |
| `estimate_analysis_calls` counts commits with `summary_beginner = None` | `tests/unit/test_commit_analysis_service.py` |
| `CommitSummaryItem` serializes both new fields via API | `tests/unit/test_api_commits.py` |
| Prompt contains dual-audience instructions | `tests/unit/test_commit_analysis_service.py` |

---

## Evaluation required

- Spot-check 5 commits from an analyzed repo: verify `summary_beginner` and
  `summary_expert` differ in vocabulary and length.
- Verify that ≥ 1 trivial commit (e.g. "Fix typo") has `summary_beginner = ""`
  or `summary_expert = ""`.

---

## Documentation impact

- `docs/prompt-contracts/commit-analysis.md`: add section on dual-audience schema.
- `specs/009-commit-audience-summaries.md`: this file.
- `docs/specs/index.md`: add row for spec 009.

---

## ADR impact

None. Pydantic optional fields + JSON blob extension is the established pattern
(used in spec 008 for `SqliteRepositoryDeleter`).

---

## Open questions

None. All decisions documented in the plan (session 2026-06-30) and confirmed by
codebase inspection.
