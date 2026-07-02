# Batch 85 — Unify tooltips (kill the double-tooltip)

## Goal

Some elements carried both the custom `data-tip` tooltip system (`#global-tip`,
`TIPS` object, `_showTip`/`_hideTip`) and a native `title=` attribute, causing two
tooltips to stack on hover/focus. Find every such element, remove the redundant
native `title=`, and fold any click-action hint that the native title used to
carry into the custom tooltip text so nothing is lost.

## What changed

- Grepped `app.js` and `index.html` for every element carrying `data-tip=`
  and cross-referenced it against every `title=` occurrence in both files.
  The **only** element with both attributes was the donut legend item in
  `loadOverview()` (`app.js`, donut chart legend build, around what were
  lines 973–976 before this batch): `data-tip="${catTipKey(c.category)}"` plus
  `title="View ${c.category} commits"`.
  - All other `title=` occurrences (GitHub link, delete button, date-picker
    inputs, activity-chart clear button, case-study timeline nodes, hotspot
    rows/table cells, contributor category badges, etc.) do **not** carry
    `data-tip` on the same element, so per the batch instructions those were
    left untouched.
- `src/git_it/static/app.js`
  - Removed `title="View ${esc(c.category)} commits"` from the donut legend
    item span.
  - `_showTip(el)`: added support for an optional `data-tip-suffix` attribute.
    When present, its value is appended to the resolved `TIPS[key]` text with a
    `\n` separator before being written to `_tipEl.textContent`. This keeps the
    shared `TIPS.cat*` entries (e.g. `catFeature`, `catBugfix`, …) unchanged —
    those same keys are also used by the non-interactive category badges in the
    Commits timeline (`data-tip="${catTipKey(...)}"` with no click behavior), so
    baking a "(Click to …)" hint directly into the shared `TIPS` entries would
    have produced a misleading tooltip on timeline rows that aren't clickable
    for that reason. A per-element suffix keeps the added hint scoped to the
    element that actually has the click behavior.
  - Donut legend item now sets `data-tip-suffix="(Click to view ${category}
    commits)"`, so the single remaining tooltip reads e.g. "Introduces new
    functionality or capabilities. Increases codebase scope.\n(Click to view
    feature commits)" — combining the category meaning (was already there) with
    the action hint the removed `title=` used to provide.
- `src/git_it/static/app.css`
  - `#global-tip`: added `white-space: pre-line;` so the `\n` inside the
    resolved tooltip text renders as a line break instead of collapsing into a
    single space (the default `white-space: normal` would otherwise swallow it).

## Tests / verification

- No JS test harness exists in this repo — none was added.
- `uv run pytest -q` — 723 passed, 12 skipped (frontend-only change).
- `uv run ruff check .` / `uv run ruff format --check .` — no findings (these
  don't cover static JS/CSS, confirms no Python regressions).
- `node --check src/git_it/static/app.js` — exits 0, confirms no JS syntax
  errors introduced.
- Static verification: re-grepped `data-tip=` and `title=` across both
  `app.js` and `index.html` after the edit to confirm the donut legend item is
  the only element that previously had both, and that it now has exactly one
  (`data-tip` + `data-tip-suffix`, no `title`).
- Live/visual verification (hover behavior, tooltip line-break rendering,
  focus-triggered tooltip) was **not** performed — Playwright MCP browser
  tools were not exercised in this session. This is a static-inspection-only
  verification for this batch.

## Gotchas

- `_showTip` previously did `text = TIPS[key] || key;` — changed to `let` so
  the suffix can be appended; behavior for elements without a suffix is
  unchanged (suffix is only appended when `dataset.tipSuffix` is truthy).
- `data-tip-override` (set by `_loadAnalyzeEstimate` on `#sh-analyze-btn`, but
  never read by `_showTip`) is a pre-existing, unrelated, apparently dead
  attribute — out of scope for this batch, left as-is.
- `white-space: pre-line` also collapses runs of spaces/tabs within each line
  (like `normal` does) while preserving explicit newlines — this matches all
  existing single-line tooltip text with no visual change for tips that don't
  use `data-tip-suffix`.

## Commits

- `fix: remove duplicate title tooltip on donut legend and unify into custom tooltip` — (SHA recorded after commit)
