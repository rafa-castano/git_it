# Spec 018: Commit-Categories Donut Multi-Select

Status: Accepted
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: AI Development Flow Agent, Quality Agent
Created: 2026-07-03
Updated: 2026-07-03

## 1. Summary

The Overview tab's "Commit Categories" doughnut chart (`src/git_it/static/app.js`)
currently cross-links to the Commits tab on click: clicking a donut slice or a
legend item switches to the Commits tab and sets the single-select `#cat-filter`
dropdown to the clicked category. This spec replaces that with donut-local,
OR-semantics **multi-select**: clicking a slice or legend item toggles that
category in/out of a selected set, the donut re-renders showing only the
selected categories (all, when none are selected), and a "Clear" affordance
resets the selection. The Commits tab's own `#cat-filter` dropdown is
unaffected and remains the way to filter the commit list by category.

## 2. Problem

`onClick` on the Chart.js doughnut instance and the `onclick` handler on each
custom legend item (`#donut-legend-custom .donut-legend-item`) both call
`switchTab('commits')` and set `#cat-filter` to the single clicked category.
This means:

- A learner cannot compare two or more categories' relative share within the
  donut itself — every click leaves the Overview tab.
- There is no multi-category selection anywhere in the UI; `#cat-filter` is a
  single `<select>`.
- The legend's `data-tip-suffix` ("Click to view X commits", added in batch 85's
  tooltip unification) describes the old cross-link behavior and would become
  misleading once clicking no longer navigates away.

## 3. Goals

- Clicking a donut slice or a legend item toggles that category in/out of a
  module-level selected-category set (`_donutSelected`), scoped to the donut
  only (does not touch `#cat-filter` or the Commits tab).
- The donut re-renders to show only the selected categories and their
  relative proportions among the selection. An empty selection means "show
  all" (the default, unfiltered view) — this is the OR semantics: the donut
  shows the union of whichever categories are checked.
- Add a "Clear" control that is visible only while a selection is active and
  resets it back to show-all.
- Give visible feedback for which legend items are currently selected
  (selected = full opacity + a selected style; unselected while a selection
  is active = dimmed), and expose the state to assistive tech via
  `aria-pressed`.
- Reconcile the batch-85 legend tooltip suffix: replace "(Click to view X
  commits)" with wording that reflects toggling instead of navigation.
- Keep the existing keyboard pattern on legend items (`tabindex="0"
  role="listitem"`, Enter/Space triggers the same handler as a click).

## 4. Non-goals

- A JS unit-test framework (none exists in this repo — see Tests required).
- Any change to the Commits tab's `#cat-filter` dropdown, its single-select
  behavior, or the timeline/commit filtering API contract.
- Any change to the activity chart, hotspot chart, or backend/API contract.
  This is Overview-tab-only, donut-only, frontend-only.
- Persisting the donut selection across `loadOverview()` reloads (repo
  switch, tab re-entry, theme toggle triggers a reload) — the selection
  resets to empty every time, matching the existing `_actScale`/`_actSpan`
  reset lifecycle from spec 017.
- Cross-linking the donut's filtered view to the Commits tab in any form.
  Dropping the donut→Commits cross-link is intentional (see Domain concepts)
  — a single click cannot both jump tabs and build a multi-selection, and the
  Commits tab keeps its own independent `#cat-filter` for that purpose.

## 5. Users

- Learner: compares two or more commit categories' relative share directly in
  the Overview tab's donut (e.g. "how much of this repo's history is bugfix
  vs. feature work?") without leaving the tab, then separately uses the
  Commits tab's `#cat-filter` when they want the underlying commit list.

## 6. User stories

```md
As a learner viewing a repository's Commit Categories donut,
I want to click one or more categories to see only their relative share,
so that I can compare specific categories without leaving the Overview tab
or being forced into a single-category view.
```

## 7. Acceptance criteria

### AC-01 — Toggling a category in and out

```gherkin
Given the donut's selected-category set is empty
When the user clicks the "Bugfix" slice or legend item
Then "BUGFIX" is added to the selected set
And the donut re-renders showing only the Bugfix slice (100% of the shown total)
When the user clicks "Bugfix" again
Then "BUGFIX" is removed from the selected set
And the donut re-renders showing all categories again (selection is empty)
```

### AC-02 — OR semantics across multiple selections

```gherkin
Given "BUGFIX" is already selected
When the user clicks the "Feature" legend item
Then "FEATURE" is added to the selected set (now {BUGFIX, FEATURE})
And the donut re-renders showing only Bugfix and Feature slices, with their
  relative proportions computed among just those two categories' counts
```

### AC-03 — Empty selection shows all categories (default view)

```gherkin
Given the selected set is empty
When the donut (re)renders
Then all categories from category_counts are shown, matching the pre-existing
  full-donut view
```

### AC-04 — Clear affordance

```gherkin
Given at least one category is selected
When the donut renders
Then a "Clear" control is visible
When the user activates "Clear"
Then the selected set becomes empty, the donut re-renders showing all
  categories, and the "Clear" control hides again
Given the selected set is empty
When the donut renders
Then the "Clear" control is not visible
```

### AC-05 — Legend visual feedback

```gherkin
Given "BUGFIX" is selected and the set is non-empty
When the legend renders
Then the "Bugfix" legend item carries a distinct selected style and
  aria-pressed="true"
And every other legend item carries a dimmed style and aria-pressed="false"
Given the selected set is empty
When the legend renders
Then no legend item carries the selected or dimmed style, and every item has
  aria-pressed="false"
```

### AC-06 — Keyboard toggling

```gherkin
Given a legend item has keyboard focus
When the user presses Enter or Space
Then the same toggle behavior as a mouse click fires (event.preventDefault()
  suppresses the default scroll-on-space)
```

### AC-07 — Tooltip wording reconciliation

```gherkin
Given a legend item's tooltip is shown (hover or focus)
Then the appended suffix reads a toggle-oriented hint (not "Click to view X
  commits", which described the removed cross-link)
And the shared TIPS category text itself (catFeature/catBugfix/...) is
  unchanged — only the per-instance data-tip-suffix changes
```

### AC-08 — No cross-link to Commits tab

```gherkin
Given the donut or a legend item is clicked
Then switchTab('commits') is never called and #cat-filter is never mutated
  as a result of this interaction
And the Commits tab's own #cat-filter dropdown continues to work exactly as
  before, independently
```

### AC-09 — Selection resets on reload

```gherkin
Given a non-empty selection is active
When loadOverview() runs again (repo switch, tab re-entry, or theme toggle)
Then the selected set is reset to empty and the donut renders show-all
```

## 8. Domain concepts

- **Selected-category set (`_donutSelected`)**: a module-level `Set` of
  upper-cased category strings (matching `#cat-filter`'s value convention,
  e.g. `"BUGFIX"`), scoped entirely to the donut. Reset to a new empty `Set`
  every time `loadOverview()` runs, mirroring spec 017's `_actScale`/`_actSpan`
  reset lifecycle.
- **OR semantics**: the donut shows the union of every selected category —
  not an intersection (there is nothing to intersect; a commit has exactly
  one category) and not a re-weighted "AND" filter. "OR" here describes how
  the set grows: each additional click adds one more category to the
  displayed union, widening what's shown rather than narrowing to a single
  category.
- **Show-all default**: an empty `_donutSelected` is the sentinel for "no
  filter" — this is a deliberate reuse of the falsy/empty-collection-means-
  unfiltered convention already used by `_actSpan === null` (spec 017) and by
  the Commits tab's own filter-clearing behavior, rather than introducing a
  separate boolean flag.
- **Dropped Commits cross-link (locked decision)**: prior behavior sent every
  donut/legend click to the Commits tab with `#cat-filter` set to the clicked
  category. That is removed. A single click cannot both build a multi-select
  state in place and navigate away; multi-select requires staying put. The
  Commits tab's `#cat-filter` remains fully functional and independent — a
  learner who wants the underlying commit list for a category still uses it
  there, just not via a donut click anymore.
- **Legend visual states**: three mutually exclusive per-item states —
  *neutral* (`_donutSelected` empty), *selected* (`_donutSelected` non-empty
  and this item is in it), *dimmed* (`_donutSelected` non-empty and this item
  is not in it). Communicated via CSS classes (`.selected`, `.dimmed`) plus
  `aria-pressed` for assistive tech, since color/opacity alone is not
  sufficient a11y signal (`frontend-a11y` posture already applied elsewhere
  in this file, e.g. the tips-toggle button's `aria-pressed`).
- **Tooltip suffix reconciliation (locked decision)**: `data-tip-suffix`
  changes from `"(Click to view {category} commits)"` to `"(Click to
  toggle)"`. The shared `TIPS.catFeature`/`catBugfix`/etc. text (used
  elsewhere, e.g. commit-row badges) is untouched — only the per-legend-item
  suffix appended in `_showTip()` changes, exactly as batch 85 designed the
  suffix mechanism to allow (see `app.js` `_showTip()` comment: "Elements
  that also act as a click target ... can append a click-action hint here
  without mutating the shared TIPS entry").

## 9. Inputs and outputs

Pure functions added to `src/git_it/static/app.js` (no DOM access, testable
in principle):

- `toggleSelection(set, cat) -> Set` — returns a **new** `Set` with `cat`
  added if absent, removed if present. Does not mutate the input `set`.
- `visibleCategories(catCounts, selected) -> Array<{category, count}>` —
  returns `catCounts` unchanged when `selected` is empty/falsy; otherwise
  returns only the entries whose upper-cased `category` is in `selected`.

DOM-touching functions (module-level state + Chart.js wiring, not unit
tested — same posture as the rest of this file):

- `_donutSelected` (module-level state, reset in `loadOverview`).
- `_rebuildDonutChart()` — recomputes `visibleCategories()`, destroys and
  rebuilds the Chart.js doughnut instance, and calls `_updateDonutLegend()`.
- `_updateDonutLegend()` — re-renders `#donut-legend-custom` with per-item
  selected/dimmed classes, `aria-pressed`, and the updated tooltip suffix;
  also toggles the "Clear" control's visibility.
- `window._toggleDonutCategory(cat)` — shared handler for both the Chart.js
  `onClick` and each legend item's `onclick`/`onkeydown`; toggles
  `_donutSelected` via `toggleSelection()` and calls `_rebuildDonutChart()`.
- `window._clearDonutSelection()` — resets `_donutSelected` to an empty
  `Set` and calls `_rebuildDonutChart()`; wired to the new "Clear" button.

No new persisted fields, API response fields, or backend changes.

## 10. Evidence requirements

Not applicable — this is a UI exploration/comparison feature, not an
evidence-grounded claim about repository history.

## 11. Failure modes

| Failure | Behavior |
|---|---|
| `category_counts` is empty (no categorized commits) | Pre-existing "No category data" empty state renders; no selection UI is shown (unchanged from today). |
| Selected set somehow contains a category no longer present in `category_counts` (should not happen given the per-load reset, but guarded) | `visibleCategories()` simply filters it out — it has no matching entry, so it contributes nothing to the rendered set; if this empties the visible set while the selection is non-empty, the donut shows a 0-slice/empty chart rather than silently falling back to show-all, so the mismatch is visible rather than masked. |
| Rapid repeated clicks on the same legend item/slice | Each click is a synchronous toggle-and-rebuild; no debounce needed (Chart.js `onClick` and the legend's plain `onclick` both fire once per genuine click, same as the pre-existing behavior). |
| User clicks a slice while `_tipsEnabled` tooltip is open | Unrelated concerns — the tooltip system operates on hover/focus independent of click handling; unaffected by this change. |

## 12. Security considerations

None. Pure client-side UI-state toggling over already-fetched, already-
rendered commit-category counts; no new data source, no new trust boundary.
Category strings are drawn from the fixed classifier enum in `CAT_COLORS`
(`FEATURE`, `BUGFIX`, `REFACTOR`, `BUILD`, `DOCS`, `TEST`, `SECURITY`,
`PERFORMANCE`, `CHORE`, `UNKNOWN`, `OTHER`), not arbitrary repository text.
The legend's inline `onclick="_toggleDonutCategory('...')"` string
interpolation mirrors the pre-existing pattern at the same call site (the
prior `cat-filter` value assignment) — not a new risk introduced by this
batch, and not hardened further here since that would be an unrelated,
separately-scoped change to this file's HTML-templating convention.

## 13. Privacy considerations

None. No new data is collected, logged, or transmitted.

## 14. Observability

None added — client-side-only UI state, no server-observable signal.

## 15. Tests required

### Automated tests

**Investigated and confirmed**: this repository has no JS unit-test
framework — no `package.json`, no `node_modules`, no Jest/Vitest/Mocha
config, no existing `*.test.js` files (same finding as specs 016 and 017).
Per CODEX.md and the tdd skill, this batch does not introduce one. The
Python `uv run pytest` suite is unaffected (no Python files touched) and
must still pass in full.

The selection/filtering logic is implemented as two small, pure,
self-contained functions (`toggleSelection`, `visibleCategories`) specifically
so it is reviewable and testable in principle, matching AC-01/AC-02/AC-03
one-to-one.

### Manual/e2e verification (Playwright, run by the orchestrator)

1. Open a repository with categorized commits in the Overview tab. Confirm
   the donut initially shows all categories (empty selection) and no "Clear"
   control is visible.
2. Click one legend item (e.g. "bugfix"). Confirm: the donut re-renders
   showing only that slice; the legend item gets a selected style and
   `aria-pressed="true"`; every other legend item dims with
   `aria-pressed="false"`; the "Clear" control appears; the Overview tab
   stays active (no tab switch); `#cat-filter` on the Commits tab is
   unchanged.
3. Click a second legend item (e.g. "feature"). Confirm both are now shown
   in the donut with proportions recomputed between just the two, and both
   legend items show the selected style.
4. Click a donut slice directly (not the legend) for a category already
   selected. Confirm it deselects (toggles off) the same way a legend click
   would.
5. Click "Clear". Confirm the donut returns to showing all categories, every
   legend item returns to the neutral (non-selected, non-dimmed) style, and
   the "Clear" control hides again.
6. Tab to a legend item via keyboard and press Enter, then Space. Confirm
   both toggle the same way a click does.
7. Hover/focus a legend item and confirm the tooltip's appended hint reads a
   toggle-oriented phrase, not "Click to view ... commits".
8. Confirm clicking the donut/legend never navigates to the Commits tab and
   never changes the Commits tab's `#cat-filter` value.

### Evaluation required

Not applicable — no LLM call, no golden-commit scoring involved.

## 16. Documentation impact

- `docs/progress/ui/batch-92-donut-category-multi-select.md` records this
  batch's work per the repository's commit/documentation discipline.
- `docs/progress/README.md` gets a new entry under `## UI` for batch 92.

## 17. ADR impact

None. Additive frontend interaction change within the existing Overview tab;
no architectural boundary changes.

## 18. Open questions

- **Should the "Clear" control be a button or reuse the legend itself (e.g.
  clicking the last-selected item again)?** Assumption made: add a small,
  explicit "Clear" button next to the "Commit Categories" heading, visible
  only while a selection is active — mirrors spec 017's reset-zoom (`⤢`)
  control precedent (a dedicated, conditionally-visible reset affordance)
  rather than relying on users discovering they can click every selected
  item back off one at a time.
- **Should selecting every available category collapse back to "show all"
  automatically?** Assumption made: no — the set stays exactly as clicked
  (all categories individually selected is representationally identical to
  the empty-set show-all view in what's rendered, but the "Clear" control
  still shows and legend items still carry the selected style, since the
  state is "all selected," not "none selected"). This keeps the toggle
  semantics simple and predictable rather than adding a special-cased
  auto-collapse rule.

## 19. Out of scope

- A JS unit-test framework/build pipeline.
- Any change to the Commits tab's `#cat-filter`, the activity chart, the
  hotspot chart, or backend/API contracts.
- Persisting the donut selection across `loadOverview()` reloads.
