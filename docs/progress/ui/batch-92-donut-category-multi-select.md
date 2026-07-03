# Batch 92 — Commit-categories donut multi-select (spec 018)

## Goal

The Overview tab's "Commit Categories" doughnut chart cross-linked to the
Commits tab on click: clicking a slice or a legend item switched to the
Commits tab and set the single-select `#cat-filter` dropdown to that one
category. This meant the donut itself could never show more than one
category's share side-by-side, and offered no way to compare categories in
place. Spec 018 replaces that with donut-local, OR-semantics multi-select:
clicking a slice or legend item toggles that category in/out of a selected
set; the donut re-renders showing only the selected categories (all, when
none are selected); and a "Clear" control resets the selection. The
Commits tab's own `#cat-filter` dropdown is untouched and keeps working
exactly as before.

## What changed

- `specs/018-donut-category-multi-select.md` — new spec (mirrors spec 017's
  structure), including the locked reconciliation decisions: the
  donut→Commits cross-link is dropped entirely (a click can't both build a
  multi-selection and navigate away), and the batch-85 tooltip suffix
  wording is updated to reflect toggling instead of navigation.
- `src/git_it/static/app.js`
  - Two new pure, DOM-free functions (placed next to the category-config
    helpers, alongside `catColor`/`catTipKey`):
    - `toggleSelection(set, cat)` — returns a **new** `Set` with `cat`
      added if absent, removed if present (does not mutate the input).
    - `visibleCategories(catCounts, selected)` — returns `catCounts`
      unchanged when `selected` is empty/falsy (show-all default);
      otherwise filters to entries whose upper-cased category is in
      `selected`.
  - New module-level state `_donutSelected` (a `Set` of upper-cased
    category strings), declared next to `_actScale`/`_actSpan` and reset to
    a new empty `Set` at the top of every `loadOverview()` call — same
    per-load reset lifecycle as spec 017's zoom state.
  - Replaced the donut-build block inside `loadOverview()` with:
    - `_rebuildDonutChart()` — computes `visibleCategories(catCounts,
      _donutSelected)`, destroys and rebuilds the Chart.js doughnut
      instance from just the visible subset, and calls
      `_updateDonutLegend()`. The Chart.js `onClick` now calls
      `window._toggleDonutCategory(cat)` instead of switching tabs.
    - `_updateDonutLegend()` — re-renders `#donut-legend-custom` with a
      `selected`/`dimmed` CSS class per item (computed from
      `_donutSelected`), `aria-pressed="true"/"false"`, the reconciled
      tooltip suffix, and toggles the new "Clear" button's visibility
      (`inline-flex` when a selection is active, `none` otherwise).
    - `window._toggleDonutCategory(cat)` — shared handler for both the
      chart's `onClick` and each legend item's `onclick`/`onkeydown`; routes
      through `toggleSelection()` then calls `_rebuildDonutChart()`.
    - `window._clearDonutSelection()` — resets `_donutSelected` to an empty
      `Set` and calls `_rebuildDonutChart()`; wired to the new "Clear"
      button.
  - Chart-box header HTML: wrapped the "Commit Categories" `<h3>` in a
    flex row with a new `#donut-clear-selection` button (hidden by
    default, `display:none`), matching the file's existing inline-styled
    control convention (mirrors spec 017's `⤢` reset-zoom button).
- `src/git_it/static/app.css`
  - `.donut-legend-item` gained a `1px solid transparent` border and
    `opacity`/`border-color` to its transition list (previously only
    `background`).
  - New `.donut-legend-item.selected` (border becomes `var(--accent)`,
    background matches the existing hover background, `font-weight: 600`)
    and `.donut-legend-item.dimmed` (`opacity: 0.45`) rules.

## Tooltip suffix reconciliation (batch 85 follow-up)

The legend item's `data-tip-suffix` changes from `"(Click to view {category}
commits)"` to `"(Click to toggle)"`. The shared `TIPS.catFeature`/
`catBugfix`/etc. text is untouched — that text is also used, unsuffixed, by
the non-interactive category badges elsewhere in the file (e.g. commit-row
badges), so only the per-legend-item suffix (appended in `_showTip()`,
exactly the mechanism batch 85 built for this purpose) changes here.

## Dropped cross-link (locked decision)

Clicking the donut or a legend item no longer calls `switchTab('commits')`
or mutates `#cat-filter`. A single click cannot both build a multi-select
state in place and navigate to another tab; multi-select requires staying
put. The Commits tab's own `#cat-filter` dropdown is fully independent and
unaffected — a learner who wants the underlying commit list for a category
still uses it there.

## Tests / verification

- No JS unit-test framework exists in this repo (confirmed via `Glob
  package.json` / `Glob **/*.test.js`, neither found — same posture as
  specs 016/017, batches 89/90). Per CODEX.md and the tdd skill, none was
  introduced. The selection/filtering logic was implemented as two small,
  pure, DOM-free functions (`toggleSelection`, `visibleCategories`)
  specifically so it is reviewable and testable in principle, mapping 1:1
  to spec 018's AC-01/AC-02/AC-03.
- `node --check src/git_it/static/app.js` — exits 0.
- `uv run ruff check .` — All checks passed.
- `uv run ruff format --check .` — 136 files already formatted.
- `uv run mypy src/` — Success: no issues found in 49 source files.
- `uv run pytest -q` — 748 passed, 12 skipped (frontend-only change; no
  Python files touched).
- Live/visual verification (clicking through multi-select, keyboard
  toggling, the Clear control, and the reconciled tooltip wording) is
  intended to be driven via Playwright by the orchestrator against a
  running instance — see spec 018 section 15 for the exact steps.

## Manual/e2e verification steps (for Playwright, see spec 018 §15)

1. Open a repo with categorized commits in the Overview tab; confirm the
   donut shows all categories and no "Clear" control is visible.
2. Click one legend item (e.g. "bugfix"); confirm the donut shows only that
   slice, the item gets the selected style and `aria-pressed="true"`, every
   other item dims with `aria-pressed="false"`, "Clear" appears, the
   Overview tab stays active, and `#cat-filter` is unchanged.
3. Click a second legend item (e.g. "feature"); confirm both slices show
   with proportions recomputed between just the two.
4. Click a donut slice directly for an already-selected category; confirm
   it deselects the same way a legend click would.
5. Click "Clear"; confirm the donut returns to show-all, every legend item
   returns to the neutral style, and "Clear" hides again.
6. Tab to a legend item and press Enter, then Space; confirm both toggle.
7. Hover/focus a legend item; confirm the tooltip's appended hint reads
   "(Click to toggle)", not the old "Click to view ... commits" wording.
8. Confirm clicking the donut/legend never navigates to the Commits tab and
   never changes `#cat-filter`.

## Gotchas

- `visibleCategories()`'s empty-selection branch (`selected.size === 0`)
  is the load-bearing "show all" default — the same falsy/empty-collection
  convention spec 017 already used for `_actSpan === null`, rather than a
  separate boolean flag.
- `_rebuildDonutChart()`'s defensive `visible.length === 0` branch (only
  reachable if `_donutSelected` somehow held a category absent from
  `catCounts`, which the UI as built cannot produce since selections only
  ever come from clicking an existing legend item) replaces
  `#chart-donut`'s container `innerHTML` with the empty-state markup. This
  mirrors the pre-existing empty-state behavior for the no-`catCounts`-at-
  all case and is flagged here as a latent, currently-unreachable edge case
  rather than something newly hardened in this batch.
- The legend item's `onclick="_toggleDonutCategory('...')"` string
  interpolation mirrors the pre-existing pattern at the same call site (the
  prior `cat-filter` value assignment) — categories are drawn from the
  fixed `CAT_COLORS` classifier enum, not arbitrary repository text, so this
  is not a new risk introduced by this batch.

## Commits

- `feat: replace donut category cross-link with local multi-select` — pending
