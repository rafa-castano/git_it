# Batch 67 — Case Study audience levels, section pruning, and timeline reload fix

## Goal

Remove two low-signal Case Study sections, add a per-audience generation and caching system so
users can switch between Beginner / Intermediate / Expert levels with instant recall of previously
generated versions, and fix the timeline not updating its content after analysis completes.

## Changes Made

### Fix 1 — Timeline content stale after analysis

**Root cause (two paths):** (1) `_pollAnalyzeStatus` only called `loadTimeline` when the timeline
panel was already visible at the moment polling detected `running: False`. If the user was watching
Deep Analysis, the in-memory `_tlAllCommits` and the selector stayed stale. (2) Switching back to
the Timeline tab via `view-btn-timeline` called `switchView` but never triggered a data reload.

**`src/git_it/static/index.html`**
- `_pollAnalyzeStatus` completion block: removed the `view-btn-timeline.active` guard. `loadTimeline`
  is now called unconditionally when `currentRepo === repoId`, regardless of active view. The panel
  is `display:none` if not visible, so the spinner flash is invisible.
- `view-btn-timeline` click listener: now also calls `loadTimeline(currentRepo)` immediately after
  `switchView('timeline')`, so navigating back to the timeline always shows fresh data.

### Fix 2 — Remove Evidence Index and Limitations from Case Study

Both sections added noise without adding teaching value: Evidence Index duplicated information
visible in commit chips; Limitations were generic caveats not specific to the repository.

**`src/git_it/repository_ingestion/application/narrative_service.py`**
- Removed `## Evidence Index` and `## Limitations` from both `_SECTIONS` (used in `_BASE_PROMPT`
  and `_BASE_INCREMENTAL_PROMPT`). New prompts contain six sections only.
- Removed the trailing "or state a limitation" clause from the evidence instruction line.

**`src/git_it/static/index.html`**
- Removed `'Evidence Index'` from `_COLLAPSIBLE_TABS`.
- Added `_HIDDEN_CS_SECTIONS = new Set(['Evidence Index', 'Limitations'])`.
- `_splitNarrative`: filters output with `.filter(s => !_HIDDEN_CS_SECTIONS.has(s.title))` so
  existing stored narratives that still contain those sections silently omit them.

### Fix 3 — Case Study audience levels with per-level caching

Users can now select Beginner / Intermediate / Expert. Switching to a cached level is instant;
switching to an uncached level triggers background regeneration with a loading state.

#### Database

**`migrations/001_initial.sql`**
- `case_studies` table: changed `repository_id TEXT PRIMARY KEY` to composite
  `PRIMARY KEY (repository_id, audience)`, added `audience TEXT NOT NULL DEFAULT 'intermediate'`.

**`src/git_it/repository_ingestion/infrastructure/sqlite.py`** (`SqliteCaseStudyStore.initialize`)
- New installs: creates table with composite PK.
- Existing installs (no `audience` column): auto-migrates by rebuilding the table as
  `case_studies_v2`, copying all rows with `audience = 'intermediate'`, dropping the old table,
  and renaming. Safe to run repeatedly — the `PRAGMA table_info` check short-circuits if already
  migrated.

**`src/git_it/repository_ingestion/infrastructure/postgres.py`** (`PostgresCaseStudyStore`)
- `save_case_study`: includes `audience` in INSERT, conflicts on `(repository_id, audience)`.
- `get_case_study(repository_id, audience="intermediate")`: filters by both columns.

The `list_repositories` join (`LEFT JOIN case_studies cs ON cs.repository_id = ir.repository_id`)
is unaffected: the `MAX(...)` aggregate with `GROUP BY repository_id` correctly returns
`has_case_study = 1` if any audience variant exists for that repo.

#### Domain

**`src/git_it/repository_ingestion/application/ports.py`**
- `CaseStudyRecord`: added `audience: str = "intermediate"` field.
- `CaseStudyStore.get_case_study`: signature changed to `(repository_id, audience="intermediate")`.

**`src/git_it/repository_ingestion/application/narrative_service.py`**
- Three audience instruction blocks (`beginner`, `intermediate`, `expert`) in `_AUDIENCE_BLOCKS`.
- `_build_system_prompt(audience)` / `_build_incremental_system_prompt(audience)` inject the
  matching block into the base prompt templates.
- `NarrativeService.generate(…, audience="intermediate")`: passes `audience` to
  `get_case_study`, `_generate_full`, `_generate_incremental`, and both `save_case_study` calls.

#### API

**`src/git_it/api/schemas.py`**
- `AnalyzeRequest.audience: str = "intermediate"` (existing field from Batch 67 draft).
- Added `RegenerateRequest(audience: str)` and `RegenStatusResponse(running: bool, audience: str)`.

**`src/git_it/api/routes/repos.py`**
- `GET /{id}/case-study`: added `audience: str = "intermediate"` query param; passes it to
  `store.get_case_study(repository_id, audience)`.
- `POST /{id}/case-study/regenerate`: starts `_regen_bg` in a daemon thread with `force=True` and
  the requested audience. Rate-limited to 5/minute. Requires API key.
- `GET /{id}/case-study/regen-status`: returns current regen state from `_regen_progress` dict.
- Added `_regen_progress: dict[str, dict]` and `_regen_progress_lock` module-level state.
- `_analyze_bg`: passes `payload.audience` through to `narrative_svc.generate(…, audience=audience)`.

#### Frontend

**`src/git_it/static/index.html`**
- CSS: `.cs-audience-wrap`, `.cs-audience-label`, `.cs-audience-select` added to Case Study styles.
- `loadCaseStudy`: reads `localStorage('cs-audience')`, appends `?audience=…` to the fetch URL.
- Chips row: renders an inline `<select>` with Beginner / Intermediate / Expert options,
  pre-selected from `localStorage`. Tooltip: "Takes effect on next analysis or regeneration".
- `_setCsAudience(value)`: saves to `localStorage`, then tries `GET /case-study?audience={value}`.
  If 200 → calls `loadCaseStudy` (instant). If 404 → calls `POST /regenerate`, shows
  "Generating {level} case study…", starts `_pollRegenStatus`.
- `_pollRegenStatus(repoId, audience)`: polls `GET /case-study/regen-status` every 2 s; calls
  `loadCaseStudy` when `running` becomes false.
- Analyze POST: includes `audience: localStorage.getItem('cs-audience') || 'intermediate'` in body.

## Files Changed

- `migrations/001_initial.sql` — fix 3
- `src/git_it/repository_ingestion/application/ports.py` — fix 3
- `src/git_it/repository_ingestion/application/narrative_service.py` — fixes 2, 3
- `src/git_it/repository_ingestion/infrastructure/sqlite.py` — fix 3
- `src/git_it/repository_ingestion/infrastructure/postgres.py` — fix 3
- `src/git_it/api/schemas.py` — fix 3
- `src/git_it/api/routes/repos.py` — fix 3
- `src/git_it/static/index.html` — fixes 1, 2, 3

## Tests Added / Fixed

### Fixed tests (hotspot churn threshold regression)

`tests/unit/test_pattern_detection_service.py` — `_record()` default churn was `10+5=15`, below the
`_HOTSPOT_MIN_CHURN=50` guard introduced in a previous batch. Fixed by updating defaults to
`total_insertions=30, total_deletions=25` (churn=55). `test_hotspot_churn_equals_insertions_plus_deletions`
updated to use explicit values that pass the churn gate (30+25=55).

### New tests — audience caching (TDD requirement)

**`tests/unit/test_sqlite_case_study_store.py`**
- `test_save_and_get_audience_specific_record` — roundtrip for `audience="beginner"`.
- `test_audience_miss_returns_none` — intermediate stored, beginner/expert queries return None.
- `test_different_audiences_stored_independently` — intermediate and beginner coexist without overwriting.
- `test_save_overwrites_same_audience_only` — upsert replaces the same audience slot only.
- `test_migration_from_single_pk_schema` — legacy single-PK table migrated; existing row readable as `intermediate`.

**`tests/unit/test_case_study_persistence.py`**
- `FakeCaseStudyStore` updated: now keys by `(repository_id, audience)` to correctly model isolation.
- `test_generate_saves_record_with_correct_audience` — saved record carries the requested audience.
- `test_different_audiences_both_call_llm` — two distinct audiences each trigger an LLM call.
- `test_same_audience_uses_cache_on_second_call` — same audience uses cache, LLM called once.

**`tests/unit/test_narrative_service.py`**
- `test_generate_beginner_audience_injects_beginner_block` — system prompt contains beginner guidance.
- `test_generate_expert_audience_injects_expert_block` — system prompt contains expert guidance.
- `test_generate_unknown_audience_falls_back_to_intermediate` — unknown audience uses intermediate block.
- `test_generate_does_not_include_removed_sections` — prompt has no "Evidence Index" or "Limitations".

## Gotchas

- The SQLite auto-migration runs inside `initialize()`. `GET /case-study` now calls
  `store.initialize()` before reading, ensuring existing DBs are migrated on first request.
- `get_repo_context` (used for narrative injection into commit analysis) always reads the
  `intermediate` audience variant — audience selection is a presentation concern, not an analysis
  context concern.
- `_regen_bg` uses `force=True`, so it always calls the LLM even if the audience variant already
  exists. This is intentional: "Regenerate" means fresh generation.
- The Postgres `initialize` function re-runs `001_initial.sql` on every boot. With
  `CREATE TABLE IF NOT EXISTS`, the new composite PK schema only applies to fresh deployments.
  Existing Postgres deployments require a manual migration (out of scope for thesis).
