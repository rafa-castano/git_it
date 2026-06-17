## Batch 49 — Visual dashboard with Chart.js

### Goal

Transform the basic HTML dashboard into a visually rich, interactive tool with Chart.js charts, dark theme, interactive commits table, and pattern signal visualizations.

### What was added

**Overview tab (new):**
- Stat cards: commits analyzed · hotspot files · patterns detected · case study status
- Category donut chart (from `category_counts` in patterns endpoint)
- Commit activity bar chart grouped by month
- Top-5 hotspot files horizontal bar chart

**Case Study tab:** metadata banner with repo URL, generated date, reading time estimate

**Patterns tab (enhanced):**
- Horizontal bar chart for top-10 hotspots, colored by confidence (green/yellow/red)
- Expandable evidence rows per file
- `conic-gradient` ratio rings for refactor wave and revert signal cards
- Migration pills: `[from] ──→ [to]  N commits`
- Architectural shifts with 🏗️/📦 icons
- Educational Insights cards with 💡

**Commits tab (enhanced):**
- Category dropdown + keyword filter bar
- Colored category badges (FEATURE blue, BUGFIX red, REFACTOR orange, DOCS purple, TEST green, BUILD gray)
- Expandable rows (click to show full summary)
- Sortable columns

**Technical:**
- Chart.js 4.x from CDN
- `_charts` registry with `destroyChart()` — prevents memory leaks on repo switch
- CSS custom properties dark theme (`--bg: #0f1117`, `--accent: #6366f1`, etc.)
- `category_counts` added to `PatternReportResponse` schema and wired in `get_patterns` route

### Tests added

3 new tests in `test_api_static.py`: Chart.js present, 4 tabs exist, category colors present

### Commits

- (Python) schemas.py + routes/repos.py: `category_counts` field added
- `9beb675 feat: enrich dashboard with charts, category badges, and interactive commits table`

---
