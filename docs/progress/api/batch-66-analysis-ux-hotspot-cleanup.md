# Batch 66 — Analysis UX improvements, hotspot tightening, and timeline cleanup

## Goal

Fix a silent analysis failure caused by a missing API key, overhaul the analysis progress UX with real commit counters and completion feedback, fix a semantic bug where "analyze 10" processed already-analyzed commits, tighten hotspot detection rules to reduce false positives, and clean up the timeline and Overview UI.

## Changes Made

### Fix 1 — `.env` loading at server startup

**Root cause:** The server launched without `ANTHROPIC_API_KEY` in its environment. The background analysis thread crashed immediately on the first LLM call, the exception was caught silently, and the frontend saw `running: False` on its first poll — making the button snap back with nothing analyzed.

**`pyproject.toml`**
- Added `python-dotenv>=1.0.0` to dependencies.

**`src/git_it/api/app.py`**
- Added `from dotenv import load_dotenv` and `load_dotenv()` at module level, before the FastAPI app is created, so all `.env` variables are available to every request handler and background thread.

### Fix 2 — Analysis semantic bug: `limit` now means "N new analyses"

**Root cause:** `_analyze_bg` called `svc.analyze_commits(limit=payload.limit, order="newest")`. This fetched the N *newest* commits from the DB — which were often already analyzed. If all N were cached, `on_progress` was called N times in rapid succession and the thread finished in < 2 seconds with 0 new analyses. The user saw the button snap to `✓ Done!` with no count change.

**`src/git_it/repository_ingestion/application/commit_analysis_service.py`**
- Added `max_new: int | None = None` parameter to `analyze_commits`.
- When `max_new` is set:
  - `total` in progress callbacks is `max_new` (the user's chosen target), not the length of all fetched commits.
  - `on_progress` is called only when a *new* LLM analysis completes — cached and skipped commits are silently bypassed.
  - The loop stops after `max_new` new analyses, regardless of how many total commits were iterated.

**`src/git_it/api/routes/repos.py`** (`_analyze_bg`)
- Changed `analyze_commits(limit=limit, ...)` to `analyze_commits(limit=None, max_new=limit, ...)`.
- `limit=None` iterates all commits in the repository; `max_new=limit` stops after the requested count of genuinely new analyses.

### Fix 3 — Analysis progress counter and completion feedback

**`src/git_it/static/index.html`** (`_pollAnalyzeStatus`)

The button now shows three distinct phases while `running: True`:

| State | Button text |
|-------|-------------|
| Initializing (no total yet) | `Running…` |
| Analyzing commits | `3/10 analyzed`, `4/10 analyzed`… |
| Generating case study (done == total, still running) | `Updating case study…` |

On `running: False`:
- Button shows `✓ Done!` in green (`var(--green)`) for 3 seconds, then resets to `+ Analyze`.
- `sh-analyzed` header badge is refreshed via `GET /analyze/estimate?limit=9999`.
- Timeline is reloaded (`loadTimeline`) if the timeline view is currently active — updates the `All (N)` selector.
- Commits tab is reloaded (`loadCommits`) if it is currently active.
- Case Study is reloaded (`loadCaseStudy`) unconditionally.

### Fix 4 — Dynamic per-status tooltip on the INGESTED badge

**Root cause:** A single `shStatus` tip described all four possible states, so hovering INGESTED showed text about COMPLETED and other statuses the user wasn't in.

**`src/git_it/static/index.html`**
- Replaced the single `shStatus` tip key with four specific ones:
  - `shStatusFull` — shown when label is `FULLY ANALYZED`
  - `shStatusIngested` — shown when label is `INGESTED`
  - `shStatusIngesting` — shown when label is `INGESTING`
  - `shStatusFailed` — shown when label is `FAILED`
- When the header status element is rendered, `dataset.tip` is set to the matching key from a lookup object.

### Fix 5 — Tighter hotspot detection rules

**Root cause:** `_DEFAULT_HOTSPOT_THRESHOLD = 5` qualified any file touched in 5+ commits, producing long lists that included lock files, documentation, CI configs, and trivially-updated config files.

**`src/git_it/repository_ingestion/application/pattern_detection_service.py`**

Three new filters applied in `detect()`:

| Rule | Before | After |
|------|--------|-------|
| Minimum commit count | 5 | **10** |
| Minimum total line churn | — | **50 lines** (`insertions + deletions`) |
| File type exclusion | — | **Excludes** lock files, `.md`, `.rst`, `.txt`, `.yml`, `.yaml`, `.toml`, `.ini`, `.cfg`, images, generated assets (`.min.js`, `.min.css`, `.map`) |
| Maximum results | unlimited | **10** |

Added constants `_HOTSPOT_MIN_CHURN = 50`, `_HOTSPOT_MAX_COUNT = 10`, `_NON_CODE_SUFFIXES`, `_NON_CODE_NAMES`, and helper `_is_code_hotspot_candidate(file_path)`.

**`src/git_it/api/routes/repos.py`**
- Updated `hotspot_threshold` query parameter default from `5` to `10`.

### Fix 6 — Remove signal highlights from timeline

The `renderTimeline` function previously injected two kinds of signal UI:
- A `tl-signals-bar` summary strip at the top (chips for Refactor Wave, Test Growth, hotspot count, revert count).
- `tl-signal-row` blocks inside each month group (one per pattern pinned to that month).

These made the timeline visually noisy and could be mistaken for actual commits.

**`src/git_it/static/index.html`**
- Removed the `summarySignals` array and its `tl-signals-bar` HTML block.
- Removed the `signalsByMonth = buildSignalIndex(patterns)` call and the per-month `tl-signal-row` render loop.
- The timeline now shows only actual commits, grouped by month.

### Fix 7 — Remove stat boxes from Deep Analysis Overview

The first row of the Overview panel contained four `.stat-card` boxes: **Commits**, **Hotspot Files**, **Patterns**, **Case Study**. These duplicated information available elsewhere and added visual noise before the charts.

**`src/git_it/static/index.html`**
- Removed the entire `<div class="stat-grid">…</div>` block from the Overview render template.
- The charts row (`<div class="charts-row">`) now begins immediately.

## Files Changed

- `pyproject.toml` — fix 1
- `src/git_it/api/app.py` — fix 1
- `src/git_it/repository_ingestion/application/commit_analysis_service.py` — fix 2
- `src/git_it/api/routes/repos.py` — fix 2, fix 5
- `src/git_it/static/index.html` — fixes 3, 4, 6, 7
- `src/git_it/repository_ingestion/application/pattern_detection_service.py` — fix 5

## Gotchas

- `analyze_commits` with `max_new` iterates **all** commits in the repository (no DB-level limit). For very large repos this could be slow; acceptable for thesis scope.
- When `max_new` is set, `on_progress(done, total)` counts only new LLM calls, not total commits processed. This is intentional — the progress bar reflects the user's target, not internal iteration.
- `buildSignalIndex` and its associated CSS classes (`.tl-signals-bar`, `.tl-signal-row`) remain in the file as dead code. They are harmless.
- The `_is_code_hotspot_candidate` check uses a lowercase name comparison, so `Dockerfile` (capital D) is caught by `"dockerfile"` in `_NON_CODE_NAMES`.

## Tests

No new unit tests. Fixes 1–4 and 6–7 are configuration or frontend interaction logic. Fix 5 (hotspot rules) has existing tests in the pattern detection test suite that continue to pass; new threshold constants are covered implicitly.
