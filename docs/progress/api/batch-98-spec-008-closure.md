## Batch 98 — Spec 008 closure (repository deletion integration test)

### Goal

Spec 008 (Repository Deletion) was functionally built — `DELETE /api/repos/{repository_id}`,
the home-card and repo-sidebar delete UI, and 8 unit tests in `tests/unit/test_api_delete.py`
all existed — but the spec header still read `**Status:** Draft` and there was no
integration-level test proving deletion removes data across the *full* read surface (list,
commits, patterns, contributors, case-study) in one continuous flow through the real FastAPI
app + SQLite DB. This batch closes that gap and truths up the docs.

### What was added

**`tests/integration/test_repo_lifecycle.py`** — new `test_delete_removes_all_data`:

- Ingests a repo via the existing `integration_client` fixture, confirms it's present in
  `GET /api/repos` and that `GET .../contributors` returns real rows (Alice, Bob).
- `DELETE /api/repos/{repository_id}` — asserts `200` and
  `{"deleted": true, "repository_id": ...}`.
- Asserts the repo is gone across every per-repo read endpoint, matched against the *actual*
  handler behavior (verified by reading `src/git_it/api/routes/repos.py`, not assumed from
  spec prose):
  - `GET /api/repos` — repo_id absent from the list.
  - `GET .../contributors` — **404** (handler explicitly 404s when the contributor reader
    finds no rows; `commit_facts` rows are gone after delete).
  - `GET .../case-study` — **404** (same contract as `test_404_on_unknown_repo`).
  - `GET .../commits` — **200** with `total == 0` (handler never 404s on an unknown/deleted
    `repository_id`; it just returns an empty result once the DB file exists).
  - `GET .../patterns` — **200** with `hotspots == []` and `bugfix_recurrences == []` (same
    reasoning as commits — the handler doesn't check repo existence).

**`docs/specs/008-repository-deletion.md`** — status bumped from `Draft` to `Implemented`.

**`docs/specs/index.md`** — spec 008 row changed from
`Draft (built, untested at integration level)` to `Implemented`.

### Tests added

- `test_delete_removes_all_data` (new, `tests/integration/test_repo_lifecycle.py`) — passes.
- Full suite: 8/8 integration lifecycle tests pass; full repo suite green (see verification
  output below).

### Gotchas

- **Spec prose vs. real behavior mismatch (documented, not fixed):** the spec's acceptance
  criteria (lines 84–86 of `docs/specs/008-repository-deletion.md`) claim
  `GET .../commits` and `GET .../patterns` return `404` after delete. The actual handlers
  never check whether `repository_id` exists — `get_commits` and `get_patterns` only guard on
  `database_is_provisioned` (a global "does *any* DB file exist" check), then run a query that
  naturally returns zero rows / an empty report for an unknown or deleted repo. This is
  pre-existing behavior, independent of deletion — the same 200-empty response happens for a
  `repository_id` that was *never* ingested, as long as some DB file exists. It is not a
  deletion bug (the underlying rows are correctly deleted by `SqliteRepositoryDeleter`); it's
  a design gap in two read endpoints that don't 404 on an absent repo. Per instructions this
  batch does not change endpoint behavior — the test asserts the real (200, empty) contract
  and documents the discrepancy in both the test docstring and this file for follow-up.
- `contributors` and `case-study` are the two endpoints that *do* 404 correctly, because their
  handlers explicitly check for "no rows found" / "record is None" rather than an implicit
  "DB file exists" check.
- There is no dedicated single-repo "detail/summary" GET endpoint distinct from
  `GET /api/repos` (the list) — confirmed by enumerating every `@router.get`/`@router.delete`
  route in `repos.py`. The task brief mentioned a "repo detail/summary" endpoint; it doesn't
  exist as a separate route, so the list endpoint is the only summary-level read surface
  tested here.

### Commits

- `test: add repository deletion integration test and close spec 008`
