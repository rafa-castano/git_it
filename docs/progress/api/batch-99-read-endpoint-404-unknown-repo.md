## Batch 99 — Read endpoints must 404 for unknown repositories (spec 008 AC alignment)

### Goal

Batch 98 (commit `c43b6b9`) documented — but did not fix — a discrepancy between
`specs/008-repository-deletion.md`'s acceptance criteria and the real handler behavior:
the spec requires `GET .../commits`, `GET .../patterns`, and `GET .../analyze/estimate`
to return `404` for an unknown/deleted `repository_id`, but the handlers only guarded on
`database_is_provisioned(...)` (a global "does *any* DB exist" check), so they returned
`200` (empty commits / empty pattern report / a zero-count estimate) for an unknown repo
on a populated database. Per `CODEX.md`'s definition-of-truth (spec outranks code), this
batch aligns the code to the spec.

### What was added

**`src/git_it/api/routes/repos.py`** — a new `_require_repository_exists(repository_id,
project_root)` helper that raises `HTTPException(404, "Repository not found.")` unless the
repository has at least one recorded ingestion run (backend-aware via
`build_ingestion_run_store`, same source of truth `delete_repo` already used). Wired into:

- `get_commits` (replaces the old `if not database_is_provisioned: return empty` guard)
- `get_patterns` (previously had no existence check at all)
- `estimate_analyze` (replaces the old `database_is_provisioned`-only guard)
- `delete_repo` (refactored to reuse the helper instead of its own inline
  "verify repository exists" block — behavior unchanged, logic deduplicated)

A **known** repository (has an ingestion run) with no commits/analyses/patterns yet still
returns its normal 200-empty result — the 404 is only for repositories that were never
ingested (or were deleted).

**Tests:**

- `tests/unit/test_api_repos.py` — added
  `test_get_commits_404_for_unknown_repo_on_populated_db`,
  `test_get_patterns_404_for_unknown_repo_on_populated_db` (RED before the fix, using the
  existing `client_empty` fixture: DB provisioned, no ingestion runs), plus
  `test_get_commits_returns_200_empty_for_known_repo_with_no_data` and
  `test_get_patterns_returns_200_empty_for_known_repo_with_no_data` as over-correction
  guards (using `client_with_repo`: a known repo with an ingestion run but no data yet).
- `tests/unit/test_api_analyze.py` — added `ingestion_runs` table + `_insert_ingestion_run`
  helper to `_init_db` (previously absent from this file's hand-rolled schema), added
  `test_estimate_404_for_unknown_repo_on_populated_db`, and wired
  `_insert_ingestion_run(db)` into the five existing "known repo" estimate tests
  (`test_estimate_returns_correct_counts`, `test_estimate_cost_proportional_to_llm_calls`,
  `test_estimate_narrative_cost_scales_with_commits` ×2 DBs,
  `test_estimate_narrative_cost_zero_when_no_commits`,
  `test_estimate_zero_calls_when_all_analyzed`) so they keep representing a known
  repository under the new existence check instead of accidentally becoming 404 cases.
- `tests/integration/test_repo_lifecycle.py::test_delete_removes_all_data` — updated the
  post-delete assertions for `GET .../commits` and `GET .../patterns` from `200`/empty to
  `404`, matching spec 008's actual contract; docstring updated to match.

### Tests added

- 5 new unit tests (2 commits/patterns 404-unknown, 2 commits/patterns 200-known-empty
  guards, 1 estimate 404-unknown).
- 1 integration test corrected (assertions only, same test function).
- Full suite: 800 passed, 18 skipped (see Gotchas for one pre-existing, unrelated flake).

### Gotchas

- **Pre-existing test-isolation flake, unrelated to this change (documented, not fixed —
  out of batch scope):** `tests/unit/test_api_delete.py::test_delete_repo_success` can fail
  with `409` instead of `200` when the full suite runs in file order. Root cause: `_analyze_progress`
  is a module-level `dict` in `repos.py` shared across the whole pytest session (not
  per-`TestClient`/per-app state), and `POST /analyze` tests in `test_api_analyze.py`
  (`test_analyze_returns_analyzing_status`, `test_analyze_accepts_any_litellm_model`) spawn
  real background daemon threads against `repository_id="repo-abc"` with no LLM
  mocking — the thread fails fast (`RuntimeError`/`AttributeError`, no API key configured)
  but the `finally` block that flips `running` back to `False` may not have executed yet by
  the time `test_api_delete.py::test_delete_repo_success` (same default `repo-abc` id) runs
  moments later, so `delete_repo`'s pre-existing "block delete while an operation is
  running" 409 check trips. Confirmed pre-existing and independent of this batch's diff by
  reproducing it with only the two unmodified analyze tests plus the unmodified delete test
  in isolation (`git diff --stat` shows zero changes to `test_api_delete.py`); it also
  disappears when `test_api_delete.py` runs alone. Not touched here per this batch's
  explicit scope (existence-check 404 behavior only — no changes to `_analyze_progress`,
  `delete_repo`'s concurrency guard, or unrelated endpoints). Flagged for a follow-up batch
  (e.g. an autouse test fixture that resets `_analyze_progress`/`_regen_progress`, or mocking
  the analysis service in those two tests).
- `tests/unit/test_api_analyze.py`'s hand-rolled `_init_db` never had an `ingestion_runs`
  table before this batch — its "known repo" tests worked purely off `commit_facts` /
  `commit_analyses` rows. Adding the existence check required adding that table and an
  insert helper to this file too (mirroring the pattern already used in
  `test_api_repos.py` and `test_api_commits.py`), otherwise those tests would have started
  failing with "no such table: ingestion_runs" (SQLite) once `estimate_analyze` began
  calling `build_ingestion_run_store(...).list_ingestion_runs_for_repository(...)`.
- Postgres fail-loud tests (`tests/unit/test_read_factories.py`) are unaffected: the
  existence check calls `build_ingestion_run_store(...)` before any other read, so an
  unreachable Postgres backend still raises the same `OperationalError` the app-level
  handler converts to `503`, regardless of which read path triggers it first.

### Commits

- `fix: 404 on unknown repository for commits, patterns, and estimate endpoints`
