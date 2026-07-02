# Batch 86 — "Clear filters" button in the Commits tab

## Goal

`#commits-filter-bar` (with a "Clear filter" button wired to
`_clearCommitFilters()`) already existed, but it was only ever shown by
`_applyCommitFilter(desc)` — the path used by cross-tab evidence/hotspot
drill-downs (e.g. clicking a hotspot bar, a bugfix-recurrence card). Manually
applying filters directly in the Commits tab (typing a keyword, picking a
category, choosing a date range, or clicking an Activity-chart bar to filter
by hour) went through `_applyTimelineFilters()` directly and never showed the
bar, so users who filtered manually had no visible/accessible way to clear
their filters short of resetting each control individually.

## What changed

- `src/git_it/static/app.js`
  - `_applyTimelineFilters()`: now calls a new `_updateCommitFilterBar(...)`
    helper with the already-computed `hasActiveFilter` flag and the filter
    values, after the existing `hasActiveFilter` computation. This is the
    single call site every filter path (keyword input, category select, date
    pickers, hour-filter chart clicks, evidence/hotspot drill-downs) already
    funnels through, so no new call sites were needed anywhere else.
  - New `_updateCommitFilterBar({ hasActiveFilter, keyword, fromDate, toDate,
    cat })`: toggles `#commits-filter-bar` visibility based on
    `hasActiveFilter`. If an evidence/hotspot filter (`_evidenceShaFilter`) is
    active, its existing descriptive label (set by `_applyCommitFilter`) is
    left alone. Otherwise it builds a short description from whichever manual
    filters are active (`Category: X`, `Search: "kw"`, `Time period selected`,
    or `Date: from – to`).
  - `_clearCommitFilters()`: **bug fix** — it reset `cat-filter`, `tl-search`,
    the date inputs, and `_evidenceShaFilter`, but never reset `_tlHourFilter`
    (the state set when a user clicks an Activity-chart bar to drill into a
    specific hour). Before this batch that gap was invisible because nothing
    reacted to `_tlHourFilter` for bar visibility. Now that the bar reacts to
    `hasActiveFilter` (which includes `_tlHourFilter`), leaving it unreset
    would make "Clear filters" appear to do nothing when an hour-filter was
    active — added `_tlHourFilter = null;` to the reset. This is the only
    change to the existing reset logic; the function's approach (read DOM
    controls, blank them, clear filter state, hide bar, re-apply) is
    unchanged and was reused as-is otherwise, per the batch instructions.
- `src/git_it/static/index.html`
  - `#commits-filter-bar` button: relabeled "Clear filter" → "Clear filters"
    (matches the plural nature of the feature — multiple filters can now
    trigger it) and its `aria-label` to "Clear all commit filters". Added a
    matching `title=` (no `data-tip` on this element, so no double-tooltip
    risk per batch 85's rule). The button was already a native `<button>`
    element, so it was already keyboard-focusable and activates with
    Enter/Space; the global `:focus-visible` rule in `app.css` already gives
    it a visible focus ring — no additional a11y wiring was needed there.
  - `#commits-filter-desc` span: added `aria-live="polite"` so screen-reader
    users are notified when the active-filter description text changes.

## Tests / verification

- No JS test harness exists in this repo — none was added.
- `uv run pytest -q` — 723 passed, 12 skipped (frontend-only change).
- `uv run ruff check .` / `uv run ruff format --check .` — no findings.
- `node --check src/git_it/static/app.js` — exits 0.
- Static trace of every path that calls `_applyTimelineFilters()` (keyword
  `oninput`, category `onchange`, date `onchange`, Activity-chart bar click,
  `_applyCommitFilter`, `_clearCommitFilters`) confirmed each now runs through
  `_updateCommitFilterBar` and gets consistent bar show/hide behavior.
- Live/visual verification (clicking around the Commits tab to confirm the
  bar appears/disappears and the button is keyboard-reachable) was **not**
  performed — Playwright MCP browser tools were not exercised in this
  session. This is a static-inspection-only verification for this batch.

## Gotchas

- If a manual filter (e.g. a keyword search) is applied *while* an
  evidence/hotspot filter is already active, the bar's description keeps
  showing the evidence label rather than folding in the extra manual filter.
  This matches pre-existing behavior (the bar was never filter-aware before
  this batch) and is a reasonable simplification, not a regression — flagged
  here rather than silently accepted.
- `_clearCommitFilters()`'s missing `_tlHourFilter` reset was a latent gap
  in existing code, not something introduced by this batch, but it had to be
  fixed here because the new bar-visibility wiring exposed it as a real
  user-facing bug ("Clear filters" appearing to do nothing after an
  hour-drill-down).

## Commits

- `feat: show Clear filters button for manually applied commit filters` — (SHA recorded after commit)
