## Batch 48 — HTML dashboard

### Goal

Add a single-page HTML dashboard served by FastAPI. No build step, no npm — pure HTML + vanilla JS. Users can browse analyzed repositories, read case studies rendered as Markdown, and explore patterns.

### What the dashboard shows

- **Sidebar**: list of all analyzed repos, click to load
- **Case Study tab**: Markdown narrative rendered via `marked.js` (CDN), with metadata chips (commit count, hotspots, generated-at)
- **Patterns tab**: hotspots table (file | commits | churn | confidence | period), refactor wave/revert signal boxes, bugfix recurrences, dependency migrations, architectural shifts, Educational Insights cards
- **Commits tab**: SHA | date | category badge | summary table with "Load more"

### Tests added

- `tests/unit/test_api_static.py` — 4 tests: root redirect, index.html served with 200, contains `/api/repos` call, `/docs` still works

### Production behavior added

- `src/git_it/api/app.py` — `StaticFiles` mount at `/static`; `GET /` redirects to `/static/index.html`; `_STATIC_DIR = Path(__file__).parent.parent / "static"` (one level up from `api/`)
- `src/git_it/static/index.html` — self-contained SPA under 600 lines; `marked.js` from CDN; sidebar + tabbed main layout; all JS inline

### Gotchas

- `_STATIC_DIR` must use `.parent.parent` not `.parent` — `app.py` is in `api/`, static is in `git_it/static/`
- `StaticFiles` raises `RuntimeError` at import time if directory doesn't exist — the directory must be on disk before tests collect (creating `index.html` creates the dir)
- mypy requires `-> None` return types and `tmp_path: Path` annotation on test functions

### Commits

- `261ad53 feat: serve static files and add root redirect to FastAPI app`
- `fc63a86 feat: add HTML dashboard with case study, patterns, and commits views`

---
