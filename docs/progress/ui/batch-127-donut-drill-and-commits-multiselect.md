## Batch 127 — Donut slice drill-to-Commits + Commits tab category multi-select

### Goal

Two related requests: (1) clicking a donut slice directly should jump to the Commits
tab filtered to that one category, and (2) the Commits tab's category filter (a
single `<select>`) should become multi-select. Both build directly on the donut's
own multi-select (spec 018, batch 92), which the user confirmed to keep as-is.

### Design decision (resolved via clarifying question before implementing)

Clicking a donut slice and clicking its legend entry currently do the exact same
thing — toggle that category into the donut's own local `_donutSelected` set
(batch 92's "chart-click and legend-click stay in sync" invariant). Making slice
clicks navigate away would silently break that invariant for one of the two
identical-until-now interactions, so this was resolved explicitly rather than
guessed on. Confirmed direction: **decouple them** — legend clicks keep toggling
the local multi-select (Overview, unchanged); slice clicks instead drill into the
Commits tab for that one category. This mirrors the Activity chart's own existing
convention (spec 017): clicking the chart *area* drills into specifics, while a
separate control (there: `−`/`+`/legend; here: the legend) adjusts the view in
place. The multi-select filter's own UI was also confirmed to reuse the donut
legend's chip style (`toggleSelection()`, `.donut-legend`/`.donut-legend-item`
classes) rather than a native `<select multiple>`, for visual/interaction
consistency with the donut's own multi-select.

### What changed

**`src/git_it/static/app.js`**

- `_rebuildDonutChart`'s chart `onClick` now calls a new
  `window._drillDonutCategoryToCommits(cat)` instead of `_toggleDonutCategory`.
  Legend `onclick` is untouched — still calls `_toggleDonutCategory`.
- `_drillDonutCategoryToCommits(cat)` — mirrors `_filterByEvidenceShas`'/spec 017's
  hour-click cross-link style: `switchTab('commits')`, ensures `_tlAllCommits` is
  loaded (`loadTimeline` if not), sets the Commits tab's category selection to
  exactly that one category (replacing, not toggling — a "drill in" action), and
  calls `_applyCommitFilter('Category: X')`.
- New Commits-tab category multi-select, mirroring the donut's own (spec 018):
  `_COMMIT_CATEGORIES` (the fixed category list), `_commitsCategorySelected` (Set,
  reset per repo load inside `loadTimeline`, not per filter application),
  `_renderCommitsCategoryChips()` (builds the same `.donut-legend-item`
  selected/dimmed chips, reusing `catColor()`/`catTipKey()` so a category shows the
  same color dot whether toggled from the donut legend or here), and
  `window._toggleCommitsCategory(cat)`.
- `_applyTimelineFilters()`: replaced the single `#cat-filter` value read with an
  OR-filter over `_commitsCategorySelected` (`commits.filter(c =>
  _commitsCategorySelected.has(...))`); `_updateCommitFilterBar` now receives a
  comma-joined description of every selected category instead of one value.
- `_clearCommitFilters()`: resets `_commitsCategorySelected` and re-renders the
  chips, alongside the existing keyword/date/evidence/hour-filter resets.
- Donut canvas `aria-label` extended with "Click a slice to view its commits in the
  Commits tab." so the new behavior is discoverable for screen-reader users, not
  just sighted ones (mirrors the care batch 85's tooltip work already put into
  discoverability).
- Fixed a stale doc comment above `_rebuildDonutChart` that described the
  now-incorrect "chart-click and legend-click stay in sync" invariant.

**`src/git_it/static/index.html`** — replaced `<select id="cat-filter">` (7
hardcoded `<option>`s) with `<div id="commits-cat-chips" class="donut-legend" ...>`,
populated by `_renderCommitsCategoryChips()`.

**Bonus fix, found while rebuilding this list (not scope creep — the exact list
being replaced):** the old `<select>`'s 7 options (`FEATURE, BUGFIX, REFACTOR,
BUILD, DOCS, TEST, OTHER`) didn't match the real `CommitCategory` domain enum
(`domain/analysis.py`: `FEATURE, BUGFIX, REFACTOR, TEST, DOCS, BUILD, SECURITY,
PERFORMANCE, CHORE, UNKNOWN`) — `SECURITY`/`PERFORMANCE`/`CHORE`/`UNKNOWN` commits
had no filter option at all, and `OTHER` isn't a real category and never matched
anything. `_COMMIT_CATEGORIES` now lists all 10 real values.

### Verification (live, via Playwright — not just described)

No JS unit-test framework exists in this repo (confirmed absence again, same
posture as batches 89/90/92/93/96/113/125/126) — live browser verification against
the real running server and a real analyzed repository (`odysseus`, 231 analyzed
commits across all 10 categories).

- Triggered `_drillDonutCategoryToCommits('FEATURE')`: switched to `tab-commits`,
  filter bar showed "Category: FEATURE", chip row showed only `feature` selected
  (others dimmed), `_commitsCategorySelected` was exactly `{FEATURE}`, and the
  rendered commit list showed only FEATURE-categorized commits (23 of 231).
- Toggled `BUGFIX` on top of that via `_toggleCommitsCategory`: commit list then
  showed the union of both categories, both chips highlighted, neither dimmed.
- `_clearCommitFilters()`: commit list returned to all 231 commits across all 10
  real categories, no chip marked selected/dimmed, selection Set empty.
- Triggered `_toggleDonutCategory('bugfix')` (the donut legend path): confirmed the
  active tab stayed `tab-overview` (no navigation) and `_donutSelected` correctly
  became `{BUGFIX}` — the legend's local-toggle behavior is unaffected by this
  batch.
- Confirmed the rebuilt chip list renders all 10 real categories (`feature,
  bugfix, refactor, test, docs, build, security, performance, chore, unknown`).
- `node --check src/git_it/static/app.js` — exits 0.

### Pinned-test fix

`tests/unit/test_api_static.py::test_static_index_has_category_colors` broke:
it asserted raw `/static/index.html` contained the literal string
`"BUGFIX"` — true only because of the now-removed hardcoded
`<option value="BUGFIX">` in the old `<select>`. The category chips are now
generated dynamically in `app.js` (same as the donut's own legend always was),
so the string no longer appears in the static HTML at all. Renamed to
`test_static_app_js_has_category_colors` and pointed at `/static/app.js`
instead — `CAT_COLORS`'s `BUGFIX` key was already there before this batch, so
the assertion's actual intent (category color data exists in the served
frontend) is preserved, just checking the file where that data has always
really lived.

### Gotchas

- `_drillDonutCategoryToCommits` sets `_commitsCategorySelected` *after* the
  `await loadTimeline(...)` guard (not before) — `loadTimeline` itself resets that
  same Set to empty on every repo load, so setting the single-category selection
  first would get silently wiped out by the reset if `_tlAllCommits` happened to
  be empty when the drill was triggered.
- `_commitsCategorySelected` must only ever be reset inside `loadTimeline` (once
  per repo load) — never inside `_applyTimelineFilters` or the toggle handler,
  or every filter interaction would wipe out the very selection being toggled.
- The multi-select filter itself was always purely client-side (`_tlAllCommits` is
  fetched once per repo load, unfiltered; category filtering happens entirely in
  `_applyTimelineFilters`'s in-memory `.filter()`) — so none of this touched the
  API, `search_commits` tool, or either SQLite/Postgres backend. Confirmed this
  before implementing, since a shared-tool contract change (used by the REST API,
  GitItGPT, and MCP) would have needed a spec, not a wiring batch.

### Commits

- `feat: drill donut slice clicks into Commits tab; make category filter multi-select`
