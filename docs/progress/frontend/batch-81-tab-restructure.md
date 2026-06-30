# Batch 81 — Tab hierarchy flatten + Timeline merge into Commits

## Goal

Remove the two-level navigation (Timeline | Deep Analysis → tabs) and replace it with
a single flat tab bar: **Overview · Case Study · Commits · Contributors**.

Timeline folds into the Commits tab, which inherits the timeline's date/keyword filters
and the original Commits tab's category filter, all unified into one filter bar. The
visual timeline rendering (grouped by month) remains the primary display.

## What changed

### HTML (`index.html`)

- Removed `.view-nav` (the Timeline | Deep Analysis top-level switcher, 2 buttons).
- Removed `#panel-timeline` outer div (previously wrapping the timeline filter bar +
  `#timeline-content`).
- Removed `#panel-detail` outer div wrapper (previously wrapping the 4 inner tabs).
- Promoted the 4 inner tab buttons and their panels to first-level children of `#main-area`.
- Overview is now the **default active tab** (`class="tab-btn active"`, `aria-selected="true"`).
- Commits tab now contains a unified filter bar:
  - `cat-filter` select (category — from old Commits tab)
  - `tl-search` text input (merged keyword search)
  - `tl-date-from` / `tl-date-to` date inputs (from old Timeline)
  - `tl-limit-select` commit count selector (from old Timeline)
- Added `#commits-filter-bar` (replaces `#commits-back-bar`) for programmatic filter labels.
- Removed `#commits-content` table, `#load-more-btn`, `← Overview` back button.
- `#timeline-content` is now inside `#tab-commits`.

### JS (`app.js`)

- Removed `switchView()` function and both `view-btn-*` event listeners.
- `selectRepo()` now calls `switchTab('overview')` + loads all data (timeline, overview,
  case study, patterns, contributors) on first select — no more lazy detail load.
- `_applyTimelineFilters()` extended with:
  - `cat-filter` value → category filter on timeline commits.
  - `_evidenceShaFilter` set → SHA-based filter (for case study evidence links).
- Donut slice onClick: removed `switchView('detail')`, now just `switchTab('commits')` +
  `_applyTimelineFilters()`.
- Donut legend items: added `onclick` + `onkeydown` — same behavior as slice click (task 8a).
- Activity chart bar onClick: removed `switchView('timeline')`, now `switchTab('commits')`
  + sets date filter inputs + `_applyTimelineFilters()`.
- `_applyCommitFilter(desc)`: now updates `#commits-filter-bar` and calls
  `_applyTimelineFilters()` instead of `renderCommitsTable`.
- `_clearCommitFilters()`: now clears `tl-search`, `tl-date-from/to`, `cat-filter` + calls
  `_applyTimelineFilters()`.
- `_filterByEvidenceShas()`: uses `_tlAllCommits` instead of `allCommits`; calls
  `loadTimeline` if commits not yet loaded.
- `_searchCommitsByFile/Keyword/SectionBody`: all switch to `tl-search` instead of
  `keyword-filter`; call `_applyCommitFilter` (which routes to timeline).
- Removed: `loadCommits()`, `renderCommitsTable()`, `toggleExpand()`, `allCommits` variable,
  `commitsLimit` variable, stale `cat-filter` change / `keyword-filter` input / `load-more-btn`
  click event listeners.
- `allCommits` references in case study narrative replaced with `_tlAllCommits`.

### CSS (`app.css`)

- Removed `.view-nav`, `.view-nav-btn`, `.view-nav-btn.active`, `.view-nav-btn:hover` rules.
- Removed `#panel-detail` flex rule.
- Removed `#load-more-btn` styles, `.expand-row`, `.expand-cell`, `tr.clickable-row`.

## Behavior verified (Playwright)

- Open repo → lands on **Overview** tab with charts loaded.
- Switching to **Commits** shows the unified filter bar + timeline visual (all 161 commits).
- Simulated donut click: `switchTab('commits') + cat=FEATURE` → timeline shows 13 FEATURE
  commits filtered correctly.
- Activity chart date filter: `from=2026-06-01, to=2026-06-30` → 13 June commits shown.
- Combined filter (FEATURE + June): 13 commits (intersection).
- `_clearCommitFilters()` → restores 161 commits, clears all filter inputs.
- Donut legend items now have the same click behavior as donut slices (task 8a resolved).

## Tests

593 passed, 8 skipped — no regressions. Frontend-only change; no new backend tests needed.

## Files changed

- `src/git_it/static/index.html` — tab structure flatten + Commits tab merge
- `src/git_it/static/app.js` — remove switchView, unify filters, merge pipeline
- `src/git_it/static/app.css` — remove view-nav + load-more-btn + expand-row CSS
- `docs/progress/frontend/batch-81-tab-restructure.md` — this file
