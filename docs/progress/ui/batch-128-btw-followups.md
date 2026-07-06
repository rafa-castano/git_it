## Batch 128 — Two `/btw` follow-ups: GitHub link underline, donut tooltip hint

### Goal

Two small, previously-noted items surfaced via `/btw`:

1. The Contributors tab's "Search on GitHub ↗" link (and the `@username ↗` variant
   when a GitHub username is known) was always underlined; should only underline on
   hover/focus, keeping the pill border as the resting-state clickability affordance.
2. Chart *elements* (not just the donut legend's chips) should hint what clicking
   does via a native Chart.js tooltip footer, mirroring the existing `data-tip-suffix`
   pattern used by the legend chips (`"(Click to toggle)"`).

### Investigation before touching anything

Checked the Activity chart's existing tooltip config first (`app.js` ~1430) — it
already has exactly this pattern, dynamically switching text by scale:
`tooltip: { callbacks: { footer: () => isFinestScale ? 'Click to view in Commits' : 'Click to zoom in' } }`.
Two other charts (Hotspots-file, Patterns) already have the same kind of footer
callback too. Only the **donut chart** was missing one — it had
`plugins: { legend: { display: false } }` with no `tooltip` key at all. So item 2's
"probably in the Activity chart bars" note turned out to already be done; the real
gap was just the donut, which is also the chart whose click behavior changed most
recently (batch 127 — slice click now drills into Commits).

### What changed

**`src/git_it/static/app.js`**

- Donut chart config gained `tooltip: { callbacks: { footer: () => 'Click to view commits for this category' } }`,
  matching the phrasing style of the other charts' footer hints and the actual
  behavior `_drillDonutCategoryToCommits` now performs (batch 127).
- Contributors' GitHub link: replaced the inline
  `style="color:var(--text);text-decoration:underline;...`* with `class="cc-gh-link"`.

**`src/git_it/static/app.css`**

- New `.cc-gh-link` rule carries the same visual properties the inline style used
  to (color, no-underline by default, pill border/radius/padding, no-wrap), plus
  `.cc-gh-link:hover, .cc-gh-link:focus-visible { text-decoration: underline; }` —
  underline now only appears on hover/keyboard-focus, not at rest.

### Verification (live, via Playwright — not just described)

No JS/CSS unit-test framework exists in this repo (confirmed absence again, same
posture as batches 89/90/92/93/96/113/125/126/127) — live browser verification.

- Read `_charts['donut'].options.plugins.tooltip.callbacks.footer` directly and
  confirmed it returns `"Click to view commits for this category"`.
- Opened the Contributors tab on a real analyzed repo, confirmed the rendered
  `.cc-gh-link` computes `text-decoration-line: none` at rest, and confirmed the
  `.cc-gh-link:hover` rule is present in the loaded stylesheet (screenshotted the
  card — no underline visible, pill border still signals clickability).
- `node --check src/git_it/static/app.js` — exits 0.
- Full suite: 954 passed, 24 skipped (unaffected — JS/CSS-only change). Checked
  specifically that `test_static_app_js_links_and_buttons_use_text_not_accent`'s
  `text.count("color:var(--text);text-decoration:underline") >= 3` pin still holds
  after removing one inline occurrence (3 remain, threshold still satisfied).

### Gotchas

- Removing the inline style entirely (rather than just dropping
  `text-decoration:underline` from it) meant checking whether any pinned test
  counted that exact inline-style substring in `app.js` — it does
  (`test_static_app_js_links_and_buttons_use_text_not_accent`), and the count was
  4 before this batch, 3 after; the test's `>= 3` threshold still passes, but a
  fourth removal in a future batch would need the same check repeated.

### Commits

- `fix: remove default underline from Contributors GitHub link; add donut click-hint tooltip`
