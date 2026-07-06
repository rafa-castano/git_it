# Bug fix session — UI fixes, analyze ordering, and audience refactor

Consolidated record of four small commits made in the same session that did not warrant individual
batch documents.

---

## Fix 1 — Analyze commits oldest-first + getting-started server command

Commit: `539bb30d39d327e5ca1030d1ced4dcbdd326cf5f`

### Problem — wrong processing order

`_analyze_bg` passed `order="newest"` to `CommitAnalysisService.analyze_commits`. Commits were
fed to the LLM in reverse chronological order, so when the incremental case study incorporated new
commits it lacked earlier historical context that the chronological narrative depends on.

### Fix — oldest-first order

`src/git_it/api/routes/repos.py`

One-line change in `_analyze_bg`:

```python
order="oldest"   # was: order="newest"
```

Commits are now processed chronologically, matching the order the case study narrative builds
the repository's engineering story.

Architectural rationale recorded in `docs/adr/009-analyze-commits-oldest-first.md` (that ADR will be
created in a later batch — reference it by that exact filename).

### Fix — uvicorn command in getting-started.md

`docs/getting-started.md`

The original "Running the server" section contained:

```bash
uv run uvicorn main:app --reload
```

Both the module path and the invocation style were wrong:
- `main:app` does not resolve — the ASGI app lives at `git_it.api.app:app`.
- `uv run uvicorn` picks up whichever environment is active in the shell, which may be a global
  `~/.venv` instead of the project venv, causing `ModuleNotFoundError: No module named 'git_it'`.

**Updated section** now shows:
1. Activate the project venv explicitly (PowerShell and bash variants).
2. `uvicorn git_it.api.app:app --reload` after activation.
3. An explanatory note about the `uv run` + global-venv conflict and how to invoke the project
   venv's executables directly without activating.

---

## Fix 2 — Remove BEFORE/AFTER boxes from Architectural Transitions

Commit: `03fac33e72f22300acd55dc19f257825a5fa4bbd`

### Problem

`_renderArchTransition` in `index.html` extracted "before" and "after" text from each transition
card using a chain of regex patterns and fell back to title-splitting heuristics. The extracted
snippets were rendered as coloured `<div class="arch-before">` / `<div class="arch-after">` boxes
with an arrow between them. In practice the regex often produced misleading or truncated text, and
the boxes added visual noise without adding clarity.

### Fix

`src/git_it/static/index.html`

- Removed all CSS rules for `.arch-transition-diagram`, `.arch-box`, `.arch-before`, `.arch-after`,
  `.arch-lbl`, and `.arch-arrow` (~8 lines).
- Removed the `bMatch`/`aMatch` regex extraction block, title-split fallback logic, and the
  `diagram` template string from `_renderArchTransition` (~26 lines of JS).
- Each transition card now renders only `<div class="cs-subcard-body"><div class="markdown-body">${rest}</div></div>` — the full marked-parsed body without the diagram prefix.

No tests changed (no JS unit tests exist for this rendering function).

---

## Fix 3 — Map all `FAILED_*` backend statuses to `FAILED` label

Commit: `c228a03a2c9be58801fc2b23f0e7da59bbb5bb4c`

### Problem

`_repoStatusLabel` in `index.html` matched only the literal string `'FAILED'`. The backend can
return granular failure codes such as `FAILED_CLONE`, `FAILED_FETCH`, etc. These fell through to
the final catch-all branch and were displayed as their raw backend value, causing a tooltip/label
mismatch and a confusing UI state.

### Fix

`src/git_it/static/index.html`

One-line change to the status check:

```js
// before
if (repo.status === 'FAILED') return { label: 'FAILED', cls: 'status-failed' };

// after
if (repo.status === 'FAILED' || (repo.status || '').startsWith('FAILED_'))
  return { label: 'FAILED', cls: 'status-failed' };
```

All `FAILED_*` variants now display the `FAILED` label with the `status-failed` CSS class.

---

## Fix 4 — Reduce Case Study audience levels from three to two

Commit: `62f5c6fc5f183d97b8003485e32f2034baba299f`

This refactor complements Batch 67 (which introduced per-audience caching) by removing the
`intermediate` level entirely. Only `beginner` and `expert` remain.

Key changes across all layers:
- Default audience changed from `"intermediate"` to `"beginner"` in ports, schemas, routes,
  SQLite store, Postgres store, and frontend `localStorage` fallback.
- `NarrativeService._AUDIENCE_BLOCKS`: intermediate block removed; unknown-audience fallback now
  resolves to `"beginner"` instead of `"intermediate"`.
- SQLite migration in `SqliteCaseStudyStore.initialize`: legacy rows with `audience='intermediate'`
  are copied as `audience='beginner'` during the v2 table rebuild.
- Frontend `<select>` reduced to two options: Beginner and Expert.
- Eleven files changed; 11 existing tests updated to replace `"intermediate"` references.
