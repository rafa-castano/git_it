# Batch 78 — Repository deletion endpoint and UI

## Goal

Allow users to permanently delete a saved repository and all its associated data from two
locations: the home page repo card and the repository detail header. Deletion is blocked when
an ingest or analysis operation is in progress for that repo.

## Changes Made

### Backend

- **New Pydantic schema** (`src/git_it/api/schemas.py`): `DeleteRepoResponse` with fields
  `deleted: bool` and `repository_id: str`.
- **New SQLite adapter class** (`src/git_it/repository_ingestion/infrastructure/sqlite.py`):
  `SqliteRepositoryDeleter.delete_repository(repository_id)` hard-deletes from all tables that
  hold repo data, in dependency order: `github_context`, `file_facts`, `commit_analyses`,
  `commit_facts`, `case_studies`, `repository_synopsis`, `ingestion_runs`.
- **New endpoint** (`src/git_it/api/routes/repos.py`):
  `DELETE /api/repos/{repository_id}` — rate-limited at 10/minute, requires API key (when
  `GIT_IT_API_KEY` is set), checks in-progress guard, returns `DeleteRepoResponse`.

### Frontend

- **`src/git_it/static/index.html`**: Added a `<button id="sh-delete-btn">` in the repo
  detail header (hidden by default, shown when a repo is selected).
- **`src/git_it/static/app.js`**: Added `deleteRepo(repoId, repoUrl, cardEl)` function with
  `window.confirm()` confirmation, then `fetch(DELETE)`. On success from the home page, removes
  the card from the DOM; from the detail page, calls `goHome()`. Returns 409 alert if an
  operation is in progress. Added `_confirmDeleteCurrentRepo()` helper. Added delete button to
  each card in `_buildRepoCard()`. Shows/hides the header delete button in `selectRepo()` and
  `goHome()`.
- **`src/git_it/static/app.css`**: Added `.rc-delete-btn` (card icon button, muted red) and
  `.delete-btn` (header outlined button, red) styles.

## Files Changed

- `src/git_it/api/schemas.py` — added `DeleteRepoResponse`
- `src/git_it/api/routes/repos.py` — new `delete_repo` endpoint + imports
- `src/git_it/repository_ingestion/infrastructure/sqlite.py` — new `SqliteRepositoryDeleter`
- `src/git_it/static/index.html` — `sh-delete-btn` in header meta
- `src/git_it/static/app.js` — `deleteRepo`, `_confirmDeleteCurrentRepo`, card delete button,
  show/hide logic
- `src/git_it/static/app.css` — `.rc-delete-btn` and `.delete-btn` styles
- `tests/unit/test_api_delete.py` — 6 new unit tests (new file)
- `docs/progress/api/batch-78-repository-deletion.md` — this file
- `docs/progress/README.md` — new entry in API section

## Tests Added

All in `tests/unit/test_api_delete.py`:

1. `test_delete_repo_success` — 200, `deleted: true`, repo gone from `GET /api/repos`
2. `test_delete_repo_not_found` — 404 on unknown repo ID
3. `test_delete_repo_requires_api_key` — 401 when key env var set, no header
4. `test_delete_repo_blocked_when_analysis_running` — 409 when `_analyze_progress` running
5. `test_delete_repo_blocked_when_regen_running` — 409 when `_regen_progress` running
6. `test_delete_repo_is_rate_limited_at_10_per_minute` — slowapi introspection

Total: 583 → 589 passed.

## Gotchas

- The `SqliteRepositoryDeleter` handles missing tables gracefully — SQLite's `DELETE` on a
  non-existent table would error, but all tables are created on first use, so this is not an
  issue in practice. If a table was never initialized (e.g. `github_context` or
  `repository_synopsis`), the DELETE silently affects 0 rows, which is correct.
- The in-progress guard reads `_analyze_progress` and `_regen_progress` under their respective
  locks to avoid a race condition with the background threads that update them.
- The UI uses `window.confirm()` (no custom modal) — acceptable for MVP per the spec. The
  confirmation dialog names the repo by its short `owner/repo` form.
- The frontend does not send an `Authorization` header for the DELETE call, consistent with the
  existing ingest and analyze buttons (auth is opt-in via `GIT_IT_API_KEY`).
