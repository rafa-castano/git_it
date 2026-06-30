# Batch 80 — Delete bug fix + commit count alignment

## Goal

Fix two backend bugs:
1. `DELETE /api/repos/{id}` crashed with `OperationalError: no such table: github_context`
   for repos that only ran ingest (no analysis, no GitHub enrichment, no case study).
2. `GET /api/repos/{id}/commits` returned `total = len(page)` instead of the real DB count,
   and offered no server-side category filter, causing donut chart counts to mismatch the
   commits list.

## Bug 1 — Delete crashes on minimal repos

**Root cause (evidence from runtime trace):**

`SqliteRepositoryDeleter.delete_repository()` issued `DELETE FROM github_context WHERE ...`
unconditionally. All optional tables (`github_context`, `file_facts`, `commit_analyses`,
`case_studies`, `repository_synopsis`) are created lazily on first write. A repo that was
only ingested — no analysis run, no GitHub enrichment, no case study — never had these
tables created. The resulting `sqlite3.OperationalError` was unhandled and propagated as a
500, which the browser displayed as "Delete failed".

**Fix (`infrastructure/sqlite.py`, `SqliteRepositoryDeleter.delete_repository`):**

Query `sqlite_master` once to collect existing table names, then delete only from tables
that exist. This is safe for all states: ingest-only, partially analysed, fully enriched.

**Regression test:** `tests/unit/test_api_delete.py::test_delete_repo_with_minimal_db_succeeds`
Creates a DB with only `ingestion_runs` and asserts DELETE returns 200.

## Bug 2 — Commit count mismatch + missing category filter

**Root cause:**

- `total` in `CommitsResponse` was `len(commits)` — the number of rows returned in the
  current page (bounded by `limit=20`). The donut chart counts all analyzed commits per
  category, so clicking "DOCS (14)" then filtering 20 newest would find at most 20 commits
  and client-side filtering returned ≤ 14, often far fewer.
- No server-side `category` parameter existed on `/commits`.

**Fix:**

- Added `count_commits_with_analyses(repository_id, category=None)` to
  `SqliteCommitWithAnalysisReader` — issues a `COUNT(*)` query (with optional
  `json_extract(ca.data, '$.category') = ?` filter).
- Extended `list_commits_with_analyses` with `category: str | None = None` parameter.
- `get_commits` route now: accepts `?category=DOCS`, passes it to both count and list
  calls, returns the true total in `CommitsResponse.total`.
- Updated `test_api_repos.py::test_get_commits_returns_paginated` to assert `total == 10`
  (DB count) not 5 (page size), documenting the corrected semantics.

**New tests:** `tests/unit/test_api_commits.py` (3 tests):
- `test_commits_total_reflects_db_count_not_page_size`
- `test_commits_category_filter_returns_only_matching`
- `test_commits_category_filter_total_is_filtered_count`

## Tests

593 passed, 8 skipped. +4 new tests (1 in `test_api_delete.py`, 3 in `test_api_commits.py`).
All pre-commit hooks (ruff, ruff format, mypy) pass.

## Files changed

- `src/git_it/repository_ingestion/infrastructure/sqlite.py` — `delete_repository` + count/filter on `list_commits_with_analyses`
- `src/git_it/api/routes/repos.py` — `get_commits` adds `category` param + true total
- `tests/unit/test_api_delete.py` — regression test for minimal-DB delete
- `tests/unit/test_api_commits.py` — new file, 3 tests for count + filter
- `tests/unit/test_api_repos.py` — updated `total` expectation in pagination test
- `docs/progress/api/batch-80-delete-fix-and-commit-count.md` — this file
