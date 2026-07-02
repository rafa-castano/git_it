# Batch 84 — Remove pattern tags from homepage repo cards

## Goal

Homepage repository cards (`renderRepoCards()` / `_buildRepoCard()`) rendered signal
pills ("⚡ Refactor Wave", "↩️ Reverts", "🧪 Test Growth", "🔥 N hotspot(s)") sourced
from a per-card `/api/repos/{id}/patterns` fetch. These pills duplicated information
already surfaced inside the repo detail view (Overview and Patterns tabs) and forced
one extra network round-trip per card just to render them, slowing down the homepage
for users with several ingested repositories. Remove the pills and the fetch that
exists solely to build them.

## What changed

- `src/git_it/static/app.js`
  - `renderRepoCards()`: removed the `Promise.allSettled` fan-out that called
    `/api/repos/{id}/patterns` for every card in `reposCache`. The function no longer
    needs to be `async` since it has no remaining `await`; changed the declaration to
    a plain `function`. Callers already invoke it without `await`, so this is behavior
    preserving.
  - `_buildRepoCard(repo)`: dropped the second `patterns` parameter and the `signals`
    array (refactor wave / revert / test growth / hotspot pills). Removed the
    `<div class="rc-patterns">...</div>` wrapper from the card markup.
- `src/git_it/static/app.css`
  - Removed the now-dead `.rc-patterns` rule. Verified via grep that
    `.rc-patterns` had no other consumer in `app.js`/`app.css` before removing.
  - `.dna-pill` and its color modifier classes (`.blue`, `.red`, `.orange`, etc.)
    were **not** removed — they're still used by the Overview tab's DNA pills and
    the Patterns tab's signal cards, both of which are unaffected by this batch.

## Tests / verification

- No JS test harness exists in this repo (no `package.json`, no jest/vitest
  config) — none was added, per instructions.
- `uv run pytest -q` — 723 passed, 12 skipped (unchanged from baseline; this is a
  frontend-only change, no Python code touched).
- `uv run ruff check .` — all checks passed.
- `uv run ruff format --check .` — 135 files already formatted.
- Static verification: grepped `app.js` and `app.css` for `_buildRepoCard` and
  `rc-patterns` after the edit — confirmed no stray references to the removed
  `patterns` parameter or the removed CSS class remain, and that `_buildRepoCard`
  is now called with a single `repo` argument at its only call site.
- Live/visual verification: Playwright MCP browser tools were not exercised in
  this session (not explicitly re-checked for availability before starting this
  batch); this batch's correctness was verified statically by reading the full
  render path (`renderRepoCards` → `_buildRepoCard` → card markup) and confirming
  the `patterns` fetch had no other consumer.

## Gotchas

- `loadPatterns(repoId)` (used by the repo detail Overview tab to populate
  `patternsData` for `_rebuildPatternsChart()`) also calls
  `/api/repos/{id}/patterns` — that call is unrelated to the homepage grid and was
  left untouched.
- `renderRepoCards()` had three other call sites (`goHome()`, `_pollForRepo`'s
  `onTick`, and the delete-repo empty-state guard) — none of them awaited the
  function's return value, so removing `async` is safe.

## Commits

- `fix: remove pattern pills and per-card patterns fetch from homepage repo cards` — `6e7a589`
