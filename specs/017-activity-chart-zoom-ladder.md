# Spec 017: Activity Chart Zoom Ladder

Status: Accepted
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: AI Development Flow Agent, Quality Agent
Created: 2026-07-03
Updated: 2026-07-03

## 1. Summary

The Overview tab's "Commit Activity" bar chart (`src/git_it/static/app.js`)
currently auto-selects one of three fixed granularities (hour/day/month) and,
on click, always jumps to the Commits tab filtered to the clicked column's
span. This spec replaces that with a full year → month → week → day → hour
zoom ladder: clicking a column drills one level finer *within the chart
itself*, explicit up/down controls let the user change scale without
clicking a column, and only a click at the finest (hour) level keeps today's
cross-link to the Commits tab. The existing `activity-date-from`/
`activity-date-to` date-box filter keeps working alongside the zoom.

## 2. Problem

`bestGranularity()` picks exactly one of `'hour' | 'day' | 'month'` for the
whole chart, based on the full commit set's date spread, and the chart never
changes granularity after that. `_buildActivityChart()`'s `onClick` always
switches to the Commits tab and sets `tl-date-from`/`tl-date-to` (and, at hour
granularity, `_tlHourFilter`) to the clicked column's span. This means a
repository with multi-year history has no way to see a month-by-month or
week-by-week shape without leaving the Overview tab, and there is no `'year'`
or `'week'` granularity at all — a user cannot zoom out to see multi-year
shape or zoom in one notch to see week-level shape without an accidental
match to day/hour granularity's date-spread thresholds.

## 3. Goals

- Replace the 3-way `bestGranularity()` with an ordered 5-rung scale enum
  (`ACTIVITY_SCALES = ['year','month','week','day','hour']`, coarsest→finest)
  used consistently by scale-stepping and bucketing logic.
- Generalize `buildActivityData()` to bucket commits at any of the 5 scales.
- Clicking a column drills exactly one scale level finer, scoped to that
  column's calendar span — except at the finest (hour) scale, where a click
  keeps today's behavior: cross-link to the Commits tab filtered to that
  hour, preserving `_tlHourFilter` semantics unchanged.
- Add visible up/down controls (`−`/`+` buttons plus a scale label) to change
  scale by one step without clicking a column; disable "finer" at `'hour'`
  and "coarser" at `'year'`.
- Persist current scale and drilled span in module-level state
  (`_actScale`, `_actSpan`), mirroring the existing `_tlHourFilter` pattern.
- Keep the `activity-date-from`/`activity-date-to` date-box filter working:
  it constrains the commit set the zoom operates on (see Domain concepts).

## 4. Non-goals

- A JS unit-test framework (see Tests required — none exists today, same
  posture as spec 016).
- Changing the Commits tab's filtering UI, the donut chart, the hotspot
  chart, or any backend/API contract. This is Overview-tab-only, frontend-only.
- Prettifying axis labels (e.g. rendering `"2024-06"` as `"Jun 2024"`). Labels
  stay as raw bucket keys, matching the existing month/day label style.
- Persisting zoom state across page reloads or across repository switches
  (state resets to an auto-picked scale on every `loadOverview()` call, same
  lifecycle as the existing `_tlAllCommits`/`window._activityAllCommits`).
- A fully general calendar-arithmetic library. Only the operations this
  ladder needs (ISO week key ↔ Monday date, month/year span bounds) are
  implemented.

## 5. Users

- Learner: explores a repository's commit activity at whatever time
  resolution is useful — zooming out for multi-year shape, zooming in for
  week/day/hour detail — without leaving the Overview tab, and still lands on
  the Commits tab when they want the underlying commit list for a specific
  hour.

## 6. User stories

```md
As a learner viewing a repository's Commit Activity chart,
I want to click a column to see a more detailed time breakdown, or use
up/down controls to change the time scale directly,
so that I can explore activity shape at whatever resolution is useful without
losing my place.
```

## 7. Acceptance criteria

### AC-01 — Ordered scale stepping

```gherkin
Given the ordered scale list ['year','month','week','day','hour']
When scaleFiner(scale) is called
Then it returns the next finer scale, or null when scale is 'hour' or invalid
When scaleCoarser(scale) is called
Then it returns the next coarser scale, or null when scale is 'year' or invalid
```

### AC-02 — Bucketing at any scale

```gherkin
Given a list of commits with committed_at timestamps spanning multiple years
When buildActivityData(commits, 'year') is called
Then labels are 4-digit years and each commit is counted under its year
When buildActivityData(commits, 'week') is called
Then labels are ISO week keys ("YYYY-Www") and each commit is counted under
  the ISO week (Monday-start) containing its committed_at date
```

### AC-03 — Initial scale auto-pick

```gherkin
Given all commits fall on a single calendar day
When bestScale(commits) is called
Then it returns 'hour'
Given commits span at most two distinct months
When bestScale(commits) is called
Then it returns 'day'
Given commits span multiple months within a single year
When bestScale(commits) is called
Then it returns 'month'
Given commits span multiple years
When bestScale(commits) is called
Then it returns 'year'
```

`bestScale()` never auto-selects `'week'` — that rung is reachable only via
drill-down or the manual zoom controls, never as the initial pick.

### AC-04 — Column click drills one level finer, scoped to the column's span

```gherkin
Given the activity chart is rendered at scale 'month' and the user clicks the
  "2024-06" column
When the click is handled
Then the chart re-renders at scale 'week', bucketing only commits whose date
  falls within June 2024 (2024-06-01..2024-06-30)
And the Overview tab remains active (no tab switch)
```

### AC-05 — Column click at the finest scale keeps today's Commits cross-link

```gherkin
Given the activity chart is rendered at scale 'hour' and the user clicks an
  hour column
When the click is handled
Then the app switches to the Commits tab, sets tl-date-from/tl-date-to to
  that hour's day, sets _tlHourFilter to that hour's prefix, and applies the
  timeline filters — identical to the pre-existing hour-click behavior
```

### AC-06 — Manual zoom controls step the scale without requiring a click

```gherkin
Given the activity chart is rendered at any scale
When the "+" (finer) control is activated
Then the scale steps one level finer (span unchanged), unless already at
  'hour', in which case the control is disabled and does nothing
When the "−" (coarser) control is activated
Then the scale steps one level coarser and, if a span is currently set, the
  span widens to the natural bucket boundaries of the new scale (see
  alignSpanToScale), unless already at 'year', in which case the control is
  disabled and does nothing
```

### AC-07 — Date-box filter and zoom span compose, not conflict

```gherkin
Given a drilled span is set (_actSpan is not null) and the user also sets an
  activity-date-from/activity-date-to date range
When the chart rebuilds
Then the rendered commit set is the intersection of the date-box range and
  the drilled span, bucketed at the current scale
```

### AC-08 — Guard cases for the pure bucketing/span functions

```gherkin
Given a bucket key and its scale
When spanForColumn(key, scale) is called
Then it returns the correct inclusive calendar span for 'year' (Jan 1–Dec
  31), 'month' (1st–last day), 'week' (Monday–Sunday of that ISO week), 'day'
  (that day only), and 'hour' (that day only, since sub-day filtering for
  hour reuses _tlHourFilter rather than a span)
```

## 8. Domain concepts

- **Scale**: one of `'year' | 'month' | 'week' | 'day' | 'hour'`, ordered
  coarsest→finest in `ACTIVITY_SCALES`.
- **Span**: `{ from, to }`, both `"YYYY-MM-DD"`, an inclusive calendar-day
  range that scopes which commits are bucketed. `null` means "no
  restriction" (the full filtered commit set).
- **ISO week key**: `"YYYY-Www"` (e.g. `"2024-W23"`), Monday-start,
  week 1 = the week containing the year's first Thursday (standard ISO-8601
  week numbering). Computed via UTC calendar arithmetic on the date-only
  portion of `committed_at` — never via local-timezone `Date` parsing — to
  match this file's existing convention of slicing ISO datetime strings
  directly rather than round-tripping them through a timezone-sensitive
  `Date` object. This avoids any local-timezone shift bugs.
- **Drill-down (click-to-drill)**: clicking a column sets `_actSpan` to that
  column's `spanForColumn()` result and steps `_actScale` one level finer via
  `scaleFiner()`. Does not apply at the finest scale (see below).
- **Finest-scale reconciliation (locked decision)**: at `'hour'` scale there
  is nothing finer to drill into, so a click keeps the pre-existing behavior
  — cross-link to the Commits tab filtered to that specific hour via
  `_tlHourFilter`. This is a deliberate behavior *change* at every other
  scale (year/month/week/day clicks no longer switch tabs — they drill the
  chart in place) and a deliberate behavior *non-change* at the hour scale.
- **Manual zoom controls**: `+`/`−` buttons step `_actScale` via
  `scaleFiner()`/`scaleCoarser()` without requiring a column click. Stepping
  finer leaves `_actSpan` unchanged (same span, finer buckets). Stepping
  coarser widens `_actSpan` (when set) to the new scale's natural bucket
  boundaries via `alignSpanToScale()`, so the chart doesn't show a coarse
  bucket size over an artificially narrow span.
- **Reset zoom**: an additional small control (`⤢`), shown only while
  `_actSpan` is set, that clears the span and re-picks the scale via
  `bestScale()` on the full (date-box-filtered) commit set. Added beyond the
  literal brief because without it a user who drills all the way in has no
  way back to the full-range view except repeatedly clicking "−" past
  'year', which is a no-op once already at 'year' with a still-narrow span.
  Flagged explicitly as an addition, not a locked requirement.
- **Date-box ↔ zoom interaction (locked decision)**: the
  `activity-date-from`/`activity-date-to` inputs and the zoom span are two
  independent, composable restrictions on the same underlying commit set.
  The date-box filter is applied first, then the zoom span, then the result
  is bucketed at the current scale (`_activityFilteredCommits()`). Changing
  the date-box range never resets `_actScale`/`_actSpan`, and drilling/zoom
  controls never touch the date-box inputs. This is the simplest of the
  options considered (the alternative — coupling the two, e.g. resetting
  zoom whenever the date box changes — was rejected as surprising: a user
  mid-drill who nudges the date range would unexpectedly lose their zoom
  level).

## 9. Inputs and outputs

Pure functions added to `src/git_it/static/app.js` (no DOM access, testable
in principle):

- `scaleCoarser(scale) -> string | null`
- `scaleFiner(scale) -> string | null`
- `isoWeekKey(dateStr) -> string`
- `isoWeekStart(weekKey) -> Date`
- `bucketKey(committedAt, scale) -> string`
- `spanForColumn(key, scale) -> { from, to }`
- `alignSpanToScale(span, scale) -> { from, to } | null`
- `commitsInSpan(commits, span) -> commits[]`
- `bestScale(commits) -> string`
- `buildActivityData(commits, scale?) -> { labels, data, scale }`

DOM-touching functions (module-level state + Chart.js wiring, not unit
tested — same posture as the rest of this file):

- `_actScale`, `_actSpan` (module-level state).
- `_buildActivityChart(filteredCommits)` (existing function, extended).
- `_activityFilteredCommits()`, `_rebuildActivityChartAtScale()`,
  `_updateActivityScaleControls()` (new, internal to `loadOverview`'s
  closure).
- `window._activityScaleCoarser()`, `window._activityScaleFiner()`,
  `window._activityResetZoom()` (new, wired to the new buttons).
- `window._rebuildActivityChart()`, `window._clearActivityDateFilter()`
  (existing, updated to compose with `_actSpan`).

No new persisted fields or API response fields are introduced.

## 10. Evidence requirements

Not applicable — this is a UI navigation/exploration feature, not an
evidence-grounded claim about repository history.

## 11. Failure modes

| Failure | Behavior |
|---|---|
| `_actScale` is unexpectedly null when `_buildActivityChart` runs | Guarded: `_buildActivityChart` falls back to `bestScale(filteredCommits)` before bucketing. |
| A drilled span excludes all commits (e.g. a sparse repo, narrow week drill) | `buildActivityData` returns empty labels; the existing "No analyzed commits yet." empty state renders (same code path used for the pre-existing empty-commit-set case) — reset-zoom control remains visible/clickable to get back to a populated view. |
| User rapidly clicks a column mid-animation | Chart.js `onClick` fires only on a genuine click; no debounce added (same as pre-existing behavior). |
| ISO week spans a year boundary (e.g. late-December dates in ISO week 1 of the next year) | Handled correctly by `isoWeekKey`'s UTC Thursday-anchoring, per the ISO-8601 algorithm — the key's year reflects the week-numbering year, not the calendar year of the clicked date. |

## 12. Security considerations

None. Pure client-side date-bucketing/UI-state logic over already-fetched,
already-rendered commit metadata; no new data source, no new trust boundary.

## 13. Privacy considerations

None. No new data is collected, logged, or transmitted.

## 14. Observability

None added — client-side-only UI state, no server-observable signal.

## 15. Tests required

### Automated tests

**Investigated and confirmed**: this repository has no JS unit-test
framework — no `package.json`, no `node_modules`, no Jest/Vitest/Mocha
config, no existing `*.test.js` files (same finding as spec 016). Per
CODEX.md and the tdd skill ("do not invent a test framework that isn't wired
up"), this batch does not introduce one. The Python `uv run pytest` suite is
unaffected (no Python files touched) and must still pass in full.

The bucketing/scale logic is implemented as small, pure, self-contained
functions (listed in Inputs and outputs) specifically so it is reviewable and
testable in principle, matching the acceptance criteria above one-to-one.

### Manual/e2e verification (Playwright, run by the orchestrator)

1. Open a repository with multi-year commit history in the Overview tab.
   Confirm the Commit Activity chart initially renders at `'year'` or
   `'month'` scale (per `bestScale`) and the scale label matches.
2. Click a year (or month) column. Confirm: the chart re-renders one level
   finer, showing only that column's span; the scale label updates; the
   Overview tab remains active (no tab switch); the "−" control is enabled.
3. Click "+" (finer) without clicking a column. Confirm the scale steps one
   level finer with the same visible span, and the finest scale disables "+".
4. Click "−" (coarser) repeatedly. Confirm the span widens at each step and
   the coarsest scale disables "−".
5. Drill down to `'hour'` scale (via clicks or "+") and click an hour column.
   Confirm the app switches to the Commits tab, filtered to that hour
   (matches pre-existing hour-click behavior — cross-check against
   `_tlHourFilter`/`tl-date-from`/`tl-date-to`).
6. With a span drilled in, set `activity-date-from`/`activity-date-to` to a
   narrower or overlapping range. Confirm the chart shows only the
   intersection, and the scale/span controls are unaffected.
7. Click the reset-zoom (`⤢`) control. Confirm the span clears, the scale
   returns to the `bestScale()` pick for the (date-box-filtered) commit set,
   and the reset control hides again until the next drill.
8. Repeat steps 1–7 on a repository with a narrow (single-day/single-hour)
   commit history to confirm the `'hour'`-initial-scale path and that "+" is
   disabled from the start.

### Evaluation required

Not applicable — no LLM call, no golden-commit scoring involved.

## 16. Documentation impact

- `docs/progress/ui/batch-90-activity-chart-zoom-ladder.md` records this
  batch's work per the repository's commit/documentation discipline.
- `docs/progress/README.md` gets a new entry under `## UI` for batch 90.

## 17. ADR impact

None. Additive frontend navigation feature within the existing Overview tab;
no architectural boundary changes.

## 18. Open questions

- **Should `'week'` ever be an auto-picked initial scale?** Assumption made:
  no — the four-tier `bestScale()` (hour/day/month/year) mirrors the
  original three-tier `bestGranularity()` plus one added tier for multi-year
  data; `'week'` stays a drill-only/manual-only rung to keep the initial
  pick predictable and matching the pre-existing thresholds as closely as
  possible for single-year repositories.
- **Should the reset-zoom control exist at all, given it isn't in the
  original brief?** Assumption made: yes, add it — without it a fully
  drilled-in user has no path back to the full-range view (see Domain
  concepts). Flagged explicitly as a deviation for reviewer sign-off.
- **Should drilling reset `activity-date-from`/`activity-date-to`, or
  vice versa?** Assumption made: no — the two stay fully independent and
  composable (see Domain concepts' locked decision). Revisit only if manual
  testing shows this is confusing in practice.

## 19. Out of scope

- A JS unit-test framework/build pipeline.
- Prettified/humanized axis labels.
- Persisting zoom state across page reloads or repository switches.
- Any change to the donut chart, hotspot chart, Commits tab filtering UI, or
  backend/API contracts.
