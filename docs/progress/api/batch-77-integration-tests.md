# Batch 77 — Integration tests for repo lifecycle flow

## Goal

Populate `tests/integration/` with integration tests covering the complete
API lifecycle from POST ingest through all read endpoints.  Tests use a real
SQLite database (no persistence mocks) and no internet access.

## Changes Made

- Created `tests/integration/__init__.py` (empty package marker).
- Created `tests/integration/conftest.py` — shared fixture with four layers
  of setup:
  1. Full DB schema pre-initialised (all five tables) so read endpoints find a
     consistent schema even before the first ingest.
  2. `repos_module.threading` replaced with `_SyncThread` (module-local patch
     only — does not affect TestClient's OS threads).
  3. `SafeGitGateway.clone_or_fetch` no-op patched — no network calls.
  4. `GitPythonCommitExtractor.extract_commits` patched to return two
     deterministic fake commits (Alice and Bob).
  5. Rate limiter reset before and after each test via `limiter._storage.reset()`
     to prevent the shared in-memory bucket from leaking between tests.
- Created `tests/integration/test_repo_lifecycle.py` — 7 integration tests.

## Files Changed

| File | Change |
|---|---|
| `tests/integration/__init__.py` | new — empty package marker |
| `tests/integration/conftest.py` | new — shared fixture |
| `tests/integration/test_repo_lifecycle.py` | new — 7 lifecycle tests |
| `docs/progress/api/batch-77-integration-tests.md` | new — this file |
| `docs/progress/README.md` | updated — API section entry |

## Tests Added

| Test | What it covers |
|---|---|
| `test_ingest_and_list` | POST ingest → GET /api/repos: repo appears with status=COMPLETED and 2 commits |
| `test_estimate_after_ingest` | POST ingest → GET analyze/estimate: all 7 schema fields present; 2 total commits, 0 analyzed |
| `test_commits_after_ingest` | POST ingest → GET commits: structure correct; list empty (no analysis run yet, INNER JOIN) |
| `test_patterns_after_ingest` | POST ingest → GET patterns: hotspots and bugfix_recurrences keys present |
| `test_contributors_after_ingest` | POST ingest → GET contributors: Alice and Bob from fake commits returned |
| `test_ingest_duplicate` | POST same URL twice → same repository_id (idempotent hash) |
| `test_404_on_unknown_repo` | GET analyze/estimate with no DB → 404 |

## Gotchas

- **Threading**: `repos.py` spawns a daemon thread per ingest.  Patching
  `threading.Thread.start` globally deadlocked the TestClient (which also
  uses threads).  Fix: patch `repos_module.threading` (the module reference in
  `repos.py`'s namespace only) with a fake namespace whose `Thread.start()`
  runs the target synchronously.
- **Missing tables**: `build_repository_ingestion_service` creates only
  `ingestion_runs`, `commit_facts`, and `file_facts`.  `GET /api/repos` does
  LEFT JOINs on `commit_analyses` and `case_studies`.  SQLite raises
  `OperationalError: no such table` if those are absent.  Fix: pre-initialise
  all five tables in the fixture.
- **Rate limiter leakage**: the in-memory rate limiter (`5/minute` on ingest)
  is a module-level global shared across tests.  After 5 integration tests each
  making one ingest call, the 6th call from `test_ingest_duplicate` got 429.
  Worse, the accumulated count leaked into the unit test suite, breaking the
  pre-existing `test_ingest_repository_id_is_deterministic`.  Fix: reset
  `limiter._storage` both in setup and teardown of the `integration_client`
  fixture.
- **commits endpoint is INNER JOIN**: after bare ingest (no analysis), the
  commits endpoint returns 0 rows because it joins `commit_analyses` INNER JOIN
  `commit_facts`.  The test documents this expected behaviour.
