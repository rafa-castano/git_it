# Batch 90 — Activity chart zoom ladder (spec 017)

## Goal

The Overview tab's "Commit Activity" chart auto-picked one of three fixed
granularities (hour/day/month, via `bestGranularity()`) and always jumped to
the Commits tab on click. There was no way to zoom out to a multi-year shape,
no `'week'` resolution, and no way to explore the chart's own time
resolution without leaving the Overview tab. Spec 017 replaces this with a
full year → month → week → day → hour zoom ladder: clicking a column drills
one level finer within the chart, explicit `−`/`+` controls step the scale
directly, and only a click at the finest (hour) scale keeps today's
cross-link to the Commits tab.

## What changed

- `docs/specs/017-activity-chart-zoom-ladder.md` — new spec (mirrors spec 016's
  structure), including the locked reconciliation decisions: only hour-level
  clicks cross-link to Commits; the date-box filter and the zoom span
  compose independently rather than resetting each other.
- `src/git_it/static/app.js`
  - Replaced `bestGranularity()`/`buildActivityData()` with an ordered
    5-rung scale ladder and a set of small, pure, DOM-free functions:
    - `ACTIVITY_SCALES` — `['year','month','week','day','hour']`, coarsest→finest.
    - `scaleCoarser(scale)` / `scaleFiner(scale)` — step one rung, `null` at
      the boundary or on an invalid scale.
    - `isoWeekKey(dateStr)` / `isoWeekStart(weekKey)` — ISO-8601 week
      key ↔ Monday-date conversion, via UTC calendar arithmetic on the
      date-only portion of the input (never local-timezone `Date` parsing).
    - `bucketKey(committedAt, scale)` — the bucket key for one commit at a
      scale. The `'hour'` format (`"YYYY-MM-DD HHh"`) is byte-for-byte
      unchanged so the existing `_tlHourFilter` cross-link keeps matching.
    - `spanForColumn(key, scale)` — the inclusive `{from, to}` calendar span
      a bucket key covers.
    - `alignSpanToScale(span, scale)` — widens/realigns a drilled span to a
      new (coarser) scale's natural bucket boundaries.
    - `commitsInSpan(commits, span)` — restricts a commit list to a span
      (`null` span = no restriction).
    - `bestScale(commits)` — the initial-scale auto-pick (generalizes
      `bestGranularity`; adds a 4th tier so genuinely multi-year data with
      more than 2 distinct months now defaults to `'year'` instead of always
      `'month'`; never auto-picks `'week'`).
    - `buildActivityData(commits, scale?)` — buckets commits at any scale
      (`scale` optional, defaults to `bestScale(commits)`).
  - New module-level state `_actScale`/`_actSpan` (declared just above
    `loadOverview`), mirroring the existing `_tlHourFilter` pattern. Reset to
    `bestScale(commitList)` / `null` every time `loadOverview()` runs.
  - `_buildActivityChart(filteredCommits)`: now buckets at `_actScale`
    (falling back to `bestScale()` if somehow unset), and its `onClick`:
    - at `'hour'` scale, keeps the pre-existing behavior exactly (switch to
      Commits tab, set `tl-date-from`/`tl-date-to` to that day, set
      `_tlHourFilter` to that hour's prefix, call `_applyTimelineFilters()`);
    - at every other scale, drills one level finer in place — sets
      `_actSpan = spanForColumn(key, _actScale)`, steps `_actScale` via
      `scaleFiner()`, and re-renders the same chart (no tab switch).
    - The pinned empty-state and container-detection lines (asserted in
      `tests/unit/test_api_static.py`) are unchanged verbatim.
  - New `_activityFilteredCommits()` — composes the `activity-date-from`/
    `activity-date-to` date-box filter with `_actSpan` (date-box first, then
    span), used by every rebuild path.
  - New `_rebuildActivityChartAtScale()` / `_updateActivityScaleControls()` —
    rebuild-and-refresh-controls helper and a controls-sync function that
    disables `−` at `'year'`, disables `+` at `'hour'`, updates the scale
    label text, and shows/hides the reset-zoom button based on whether
    `_actSpan` is set.
  - New `window._activityScaleCoarser()` / `window._activityScaleFiner()` /
    `window._activityResetZoom()` — wired to the new buttons.
  - `window._rebuildActivityChart()` / `window._clearActivityDateFilter()` —
    updated to route through `_activityFilteredCommits()` /
    `commitsInSpan(..., _actSpan)` so the date-box filter keeps composing
    with whatever zoom span is currently set, instead of ignoring it.
  - Chart header HTML: added a `−` / scale-label / `+` / `⤢` (reset,
    hidden unless drilled) control group next to the existing date-range
    inputs, with `aria-label`s and `title`s matching the file's existing
    inline-styled-button convention.

## Week-key convention

ISO-8601 week numbering, Monday-start, `"YYYY-Www"` (e.g. `"2024-W23"`). Week
1 is the week containing the year's first Thursday, computed by shifting the
UTC date to that week's Thursday and reading its calendar year — the
standard ISO algorithm. All arithmetic uses `Date.UTC`/`getUTCDay`/
`setUTCDate` on the date-only (`Y-M-D`) portion of `committed_at`, never a
local-timezone `Date` parse, to match this file's existing convention of
slicing ISO datetime strings directly. Verified manually (see Tests /
verification) that ISO week keys correctly roll over a year boundary in both
directions (`"2023-01-01"` → `"2022-W52"`, `"2024-12-31"` → `"2025-W01"`).

## Date-box ↔ zoom interaction

The `activity-date-from`/`activity-date-to` inputs and the drilled zoom span
(`_actSpan`) are independent, composable restrictions on the same commit
set: the date-box filter is applied first, then the zoom span, then the
result is bucketed at `_actScale` (`_activityFilteredCommits()`). Neither
resets the other. This was the simplest of the options considered — coupling
them (e.g. resetting zoom whenever the date range changes) was rejected as
surprising for a user mid-drill. See spec 017 section 8 (Domain concepts) for
the full rationale.

## Deviation from the brief

Added a small reset-zoom control (`⤢`, `window._activityResetZoom()`),
visible only while `_actSpan` is set, that clears the span and re-picks the
scale via `bestScale()`. This was not explicitly requested — without it, a
fully drilled-in user has no way back to the full-range view except
repeatedly clicking `−`, which becomes a no-op once already at `'year'` scale
with a still-narrow span. Flagged here and in the spec's Open questions for
explicit reviewer sign-off; easy to remove if deemed unnecessary scope.

## Tests / verification

- No JS unit-test framework exists in this repo (confirmed via
  `Glob package.json` / `Glob **/*.test.js` — neither found), same posture as
  spec 016 (batch 89). Per CODEX.md and the tdd skill, none was introduced.
  The bucketing/scale logic was implemented as small, pure, DOM-free
  functions specifically so it is reviewable and testable in principle
  (listed above), each mapping 1:1 to an acceptance criterion in spec 017.
- Manual verification via a throwaway Node.js script (outside the repo,
  not committed) that `eval`'d the extracted pure-function block and
  exercised: `scaleFiner`/`scaleCoarser` boundary `null`s at `'hour'`/`'year'`;
  `isoWeekKey` values and year-boundary rollover; `spanForColumn` for all 5
  scales; `alignSpanToScale` widening week→month and month→year;
  `commitsInSpan` filtering; `bestScale` across single-day, ≤2-month,
  single-year-multi-month, and multi-year-multi-month commit sets (the last
  needed a realistic multi-point fixture — a 2-commit, 2-year-apart fixture
  degenerates to the `months.size<=2` tier and returns `'day'`, an inherited
  quirk from the original `bestGranularity()`'s same threshold, not a new
  regression); `buildActivityData` at `'week'` scale. All matched expected
  values.
- `node --check src/git_it/static/app.js` — exits 0.
- `uv run ruff check .` — All checks passed.
- `uv run ruff format --check .` — 136 files already formatted.
- `uv run mypy src/` — Success: no issues found in 49 source files.
- `uv run pytest -q` — 748 passed, 12 skipped (frontend-only change; the two
  pinned assertions in `tests/unit/test_api_static.py` against
  `_buildActivityChart`'s empty-state and container-detection lines still
  pass since those lines were kept verbatim).
- Live/visual verification (clicking through the zoom ladder, exercising the
  up/down controls, confirming the hour-click Commits cross-link) was **not**
  performed in this session — see spec 017 section 15 for the exact
  Playwright verification steps the orchestrator will drive against a
  running instance.

## Manual/e2e verification steps (for Playwright, see spec 017 §15)

1. Open a multi-year repo's Overview tab; confirm the chart's initial scale
   label matches `bestScale()`'s pick.
2. Click a coarse column (e.g. a year or month bar); confirm the chart
   re-renders one level finer scoped to that column's span, the Overview tab
   stays active, and the `−` control becomes enabled.
3. Click `+` without clicking a column; confirm the scale steps one level
   finer with the same span, and `+` disables at `'hour'`.
4. Click `−` repeatedly; confirm the span widens each step and `−` disables
   at `'year'`.
5. Drill to `'hour'` scale and click an hour column; confirm it switches to
   Commits filtered to that hour (same as pre-existing behavior).
6. With a span drilled in, set the date-box range to an overlapping/narrower
   range; confirm the chart shows only the intersection.
7. Click the reset (`⤢`) control; confirm the span clears and the scale
   returns to the `bestScale()` pick.
8. Repeat 1–7 on a single-day/single-hour-history repo to confirm the
   `'hour'`-initial-scale path and that `+` is disabled from the start.

## Gotchas

- `bestScale()`'s tier thresholds are evaluated in order (days ≤ 1 → hour;
  months ≤ 2 → day; years ≤ 1 → month; else → year), inherited unchanged
  from the original `bestGranularity()` for the first two tiers. A sparse,
  widely-spaced commit set with only 2 distinct months of activity (even if
  those two months are years apart) still resolves to `'day'`, not `'year'`
  — this is a pre-existing threshold quirk, not something this batch
  introduced or regressed.
- The `'hour'` bucket-key format (`"YYYY-MM-DD HHh"`) and the `_tlHourFilter`
  cross-link contract were kept byte-for-byte identical on purpose — any
  drift there would silently break the existing Commits-tab hour filter.
- Non-finest-scale clicks no longer switch to the Commits tab — this is a
  deliberate, spec-locked behavior change from the pre-existing "every click
  jumps to Commits" behavior (see spec 017 §8, "Finest-scale reconciliation").

## Commits

- `feat: add zoom ladder (year-hour) to activity chart with drill and controls` — `786b125`
