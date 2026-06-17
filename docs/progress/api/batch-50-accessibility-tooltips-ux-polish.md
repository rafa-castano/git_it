## Batch 50 — Accessibility, tooltips, and UX polish

### Goal

Bring the dashboard to WCAG 2.1 AA compliance and make it production-ready for demos: full tooltip coverage for every technical term, correct ARIA semantics, keyboard navigation, contrast fixes, and quality-of-life UX controls.

### What was added

**Accessibility (WCAG 2.1 AA):**
- All tab buttons: `role="tab"`, `aria-selected`, `aria-controls`; container: `role="tablist"` + `aria-label`; panels: `role="tabpanel"`, `aria-labelledby`, `tabindex="0"`
- Sidebar items: `tabindex="0"`, `role="listitem"`, keyboard activation (Enter/Space)
- All filter inputs: `aria-label` attributes
- All charts: `aria-label` on `<canvas>`
- Spinner: `role="status"` + `aria-label`
- Tables: `scope="col"` on `<th>`, wrapped in `div.table-wrap`
- Global `:focus-visible` ring (`outline: 2px solid var(--accent)`)

**Contrast fixes:**
- `--muted` changed from `#64748b` → `#94a3b8` (6.9:1 ratio on dark bg)
- `.repo-meta` switched from `opacity: 0.75` to explicit `color: #8b9ab5` (opacity-based dimming is not contrast-safe)

**Tooltip system:**
- Single `#global-tip` div with `role="tooltip"` and `position: fixed` — avoids z-index/overflow issues
- Event delegation on `document` (mouseover / mouseout / focusin / focusout)
- All tooltip text in a `TIPS` object with stable keys
- Tooltips on: hotspot section, pattern signals, DNA pills, commit category badges, risk level badges, column headers, dependency migration confidence, donut legend swatches, section headings

**Donut chart legend:**
- Chart.js built-in legend disabled (canvas-rendered, not accessible)
- Replaced with custom HTML `.donut-legend` below the chart — each swatch has `data-tip` for category explanation

**Commits tab fix:**
- Bug: all categories showed "—" — root cause: `commit_facts` has 1548 commits, `commit_analyses` only 30. Default newest-first query returned commits with no analysis data
- Fix: flipped to `INNER JOIN` starting from `commit_analyses`, so only analyzed commits are returned
- Also fixed `analysis_data.get("importance")` → `analysis_data.get("risk_level")`
- 3 tests updated to insert analysis records alongside commit_facts

**UX improvements:**
- Revert Signal tooltip adapts to value: count 0 → green card + "No reverts — positive stability signal"; count > 0 → red card + warning text
- Architectural Shifts section removed (noise with current data)
- "Load more" button hidden when `commits.length >= total` (all loaded)
- Hotspots with `confidence < 0.70` filtered out from all views (Overview chart, Patterns chart, evidence table, stat card count)
- GitHub button in subheader: pill with GitHub SVG logo + repo short name, highlights on hover
- Tooltip toggle button in header (starts active; toggles `_tipsEnabled` flag)
- Light/dark mode button: CSS custom property override via `[data-theme="light"]` on `<html>`

### Skill created

- `~/.claude/skills/frontend-a11y/SKILL.md` — WCAG 2.1 AA audit checklist with severity levels (CRITICAL/MAJOR/MINOR), contrast ratio formulas, ARIA patterns, tooltip implementation, and dark-theme specifics

### Tests added

3 new tests in `test_api_static.py`: ARIA roles present, tooltip system present, `lang="en"` attribute

### Gotchas

- Chart.js legend is canvas-rendered — no HTML elements to attach `data-tip` to. Must disable and replace with custom HTML
- `taskkill /F /PID` fails in Git Bash (converts `/F` to a path) — use `cmd //c "taskkill /F /PID <pid>"`
- `opacity: 0.75` is not contrast-safe — always use explicit color values for WCAG compliance

### Commits

- `bea0042 feat: add tooltips, ARIA roles, focus styles, and a11y improvements to dashboard`
- `7986e08 feat: replace Chart.js donut legend with HTML legend with per-category tooltips`
- `933e47f fix: adaptive revert signal tooltip and remove architectural shifts noise`
- `b6eb54a fix: hide Load more button when all commits are already loaded`
- `ae9dc02 fix: filter hotspots below 70% confidence from all views`
- `9d915e5 feat: GitHub button, tooltip toggle, and light/dark mode switch in header`
