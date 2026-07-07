## Batch 150 — RefreshAllService application service (spec 028, slice 1)

### Goal

Implement the first slice of spec 028 (Refresh All Repositories): a new application
service that enumerates every already-ingested repository and re-runs the free
commit-corpus refresh (`git fetch` + commit-fact re-extraction) for each, isolating any
per-repository failure so one broken upstream never aborts the batch. The CLI command
(batch 151), API endpoint (batch 152), and dashboard button are explicitly out of scope
for this slice.

### Why

Today the only way to pull commits pushed upstream since a repository was first ingested
is to re-paste its URL into the home search box, one repository at a time. Spec 028 adds a
single "refresh all" action for that, built as a thin batch loop over the existing
per-repository ingest flow — no new ingestion mechanism, no new dependency. The locked
design point (spec 028 Goal 3a): refresh-all must call `RepositoryIngestionService.ingest`
directly and must never route through the `_ingest_bg` wrapper in `api/routes/repos.py`,
because that wrapper (not `ingest` itself) is where the paid discussion/release/advisory
evidence summarizers live — refresh-all is locked free.

### What was added

**`application/refresh_all_service.py`** (new)
- `RefreshIngestPrimitive` — a local `Protocol` with a single `ingest(raw_url) ->
  IngestionResult` method, mirroring `RepositoryIngestionService.ingest`'s signature.
  `RepositoryIngestionService` (`application/service.py`) satisfies it structurally
  without any changes — this service depends on the one method it calls, not the concrete
  class, consistent with the hexagonal boundary the rest of the module keeps.
- `IngestServiceFactory` — a `Callable[[str], RefreshIngestPrimitive]` type alias. Because
  `RepositoryIngestionService` is built per-repository (its bare-cache path and
  `repository_id` are constructor arguments — see `build_repository_ingestion_service` in
  `composition.py`), `RefreshAllService` is given a factory rather than one pre-built
  instance, and calls it once per enumerated repository.
- `RepositoryRefreshResult` — frozen dataclass: `repository_id`, `canonical_url`,
  `status` (`"completed"` | `"failed"`), `new_commits`, `error_code`, `safe_message`.
- `RefreshAllResult` — frozen dataclass: `repositories` (list of the above),
  `total_repositories`, `refreshed_count`, `failed_count`, `total_new_commits`, plus a
  `nothing_to_refresh` property (`total_repositories == 0`) for the empty-list case.
- `RefreshAllService(repository_list_reader, ingest_service_factory)` — keyword-only,
  depends only on the existing `RepositoryListReader` port plus the new
  `IngestServiceFactory`.
  - `refresh_all() -> RefreshAllResult` — calls `list_repositories()` once; returns a
    shared `_EMPTY_RESULT` singleton with zero ingest calls when the list is empty.
    Otherwise builds one ingest primitive per repository (via the factory) and calls
    `.ingest(repo.canonical_url)` for each, sequentially (spec 028 defers concurrency).
  - `_refresh_one(repo)` — wraps the factory call and `.ingest()` call in
    `try/except Exception`; a raised exception is caught, logged as
    `_logger.warning("refresh failed: %s", type(exc).__name__, extra={"repository_id":
    ...})` (never the raw exception message — this is the safety property a planted
    `RuntimeError("... token=ghp_...")` regression test enforces), and mapped to a failed
    result whose `safe_message` is `f"Refresh failed: {type(exc).__name__}"`. Separately,
    an `IngestionResult` whose `status != "COMPLETED"` (any of the `_FAILED_STATUSES`
    values from `interfaces/cli.py`, checked here as "not COMPLETED" rather than importing
    that interfaces-layer set, to keep the application layer from depending on
    `interfaces/`) is mapped to a failed result carrying that result's own
    `error_code`/`safe_message` unchanged — both are already safe by construction
    (`IngestionResult.safe_message` never carries a raw exception). Either failure path
    lets the loop continue with the remaining repositories.
  - A successful (`"COMPLETED"`) result maps `new_commits = result.commits_inserted or 0`.

**`composition.py`**
- New import: `RefreshAllService` from the new module (inserted alphabetically after
  `ports`, before `release_summarizer`).
- `build_refresh_all_service(*, project_root) -> RefreshAllService` — wires
  `build_repository_list_reader(project_root=project_root)` for enumeration and a local
  closure `ingest_service_factory(repository_id) ->
  build_repository_ingestion_service(project_root=project_root,
  repository_id=repository_id)` for the per-repo ingest primitive. No analysis/narrative/
  summarizer collaborator is wired anywhere in this factory — the free-only lock holds
  structurally, not just by convention, since `RefreshAllService` has no port through
  which it could reach one.

### How the free-only lock was verified

Read `application/service.py` (`RepositoryIngestionService.ingest`) in full: it calls
only `git_gateway.clone_or_fetch`, the optional `default_branch_reader`/`writer` pair, the
optional `project_doc_reader`/`writer` pair, and the optional `commit_extractor` +
`commit_fact_writer`/`file_fact_writer` pair — no discussion/release/advisory summarizer
is imported or called anywhere in that file. Separately read `api/routes/repos.py`'s
`_ingest_bg`: it calls `svc.ingest(url)` first, then — only if `result.status ==
"COMPLETED"` — calls `_fetch_and_store_repo_metadata`, `_fetch_and_store_discussion_evidence`,
`_fetch_and_store_release_evidence`, and `_fetch_and_store_advisory_evidence` (the paid,
`GITHUB_TOKEN`-gated summarizer calls) as a separate step *after* `ingest()` returns, in
the wrapper, not inside `ingest()`. `RefreshAllService` and `build_refresh_all_service`
call `RepositoryIngestionService.ingest` directly and never construct or invoke
`_ingest_bg` or any of those four helpers — confirmed both by code reading and by the
`test_refresh_all_never_invokes_any_analysis_collaborator` regression test, which injects
a fake ingest primitive whose `analyze_commits` method raises `AssertionError` if ever
called, then asserts it was never touched after a full `refresh_all()` run.

### Real symbols grounded on

- `RepositoryListReader.list_repositories() -> list[RepositoryRecord]` and
  `RepositoryRecord(repository_id, canonical_url, status, commit_count, analysis_count,
  has_case_study)` — `application/ports.py`.
- `build_repository_list_reader(*, project_root) ->
  SqliteRepositoryListReader | PostgresRepositoryListReader` — `composition.py`.
- `RepositoryIngestionService.ingest(raw_url) -> IngestionResult` — `application/service.py`.
- `IngestionResult(status, error_code, stage, retryable, safe_message, run_id,
  canonical_url, commits_inserted, commits_reused, files_inserted, files_reused)` —
  `application/service.py`. Note: `_FAILED_STATUSES` (`FAILED_VALIDATION`, `FAILED_FETCH`,
  `FAILED_EXTRACTION`, `FAILED_PERSISTENCE`, `LIMIT_EXCEEDED`, `CANCELLED`) is defined in
  `interfaces/cli.py`, not `application/service.py`. Rather than import an
  interfaces-layer constant into the application layer, `RefreshAllService` treats any
  `status != "COMPLETED"` as failed — `"COMPLETED"` is the only success status
  `RepositoryIngestionService.ingest` ever constructs (`service.py` line 150), so this is
  equivalent without the layering violation.
- `build_repository_ingestion_service(*, project_root, repository_id, ...) ->
  RepositoryIngestionService` — `composition.py`; confirmed it requires `repository_id`
  per call (the git cache path and run/commit/file stores are repository-scoped), which is
  why `RefreshAllService` takes an `IngestServiceFactory` rather than one prebuilt service.

### `RefreshAllResult` shape (for batches 151/152)

```python
RepositoryRefreshResult(
    repository_id: str,
    canonical_url: str,
    status: str,  # "completed" | "failed"
    new_commits: int,
    error_code: str | None,
    safe_message: str | None,
)

RefreshAllResult(
    repositories: list[RepositoryRefreshResult],
    total_repositories: int,
    refreshed_count: int,
    failed_count: int,
    total_new_commits: int,
)
# .nothing_to_refresh property == (total_repositories == 0)
```

### Tests added

`tests/unit/test_refresh_all_service.py` (6 new tests), fakes only (`_FakeRepositoryListReader`,
`_SpyIngestPrimitive`), mirroring the injection style of `test_embedding_backfill_service.py`:
- `test_enumerates_repositories_and_invokes_ingest_once_per_repository` — enumeration:
  `list_repositories()` drives exactly one `ingest()` call per repository, with each
  repo's `canonical_url`.
- `test_new_commits_surfaces_ingestion_result_commits_inserted` — result mapping:
  `IngestionResult.commits_inserted` surfaces unchanged as `new_commits`.
- `test_one_repository_raising_is_isolated_and_others_still_refresh` — a raised
  `RuntimeError` (with a planted fake token in its message) for one of three repos is
  caught; the other two still complete; the surfaced `safe_message` contains
  `"RuntimeError"` but never the planted token string — the security regression this spec
  requires.
- `test_one_repository_with_failed_ingestion_status_is_isolated` — a non-`COMPLETED`
  `IngestionResult` (`FAILED_FETCH`) for one of two repos marks only that repo failed,
  carrying its `error_code`/`safe_message` through unchanged; the other repo still
  completes.
- `test_no_repositories_reports_nothing_to_refresh_and_makes_no_ingest_calls` — empty
  case: `nothing_to_refresh is True`, zero ingest calls.
- `test_refresh_all_never_invokes_any_analysis_collaborator` — the free-only lock,
  described above.

`tests/unit/test_repository_ingestion_composition.py` (+2 tests):
- `test_build_refresh_all_service_wires_repository_list_reader` — the built service's
  `_repository_list_reader` is a `SqliteRepositoryListReader` (no `DATABASE_URL`).
- `test_build_refresh_all_service_factory_builds_ingestion_service_per_repository` —
  calling `service._ingest_service_factory("repo-abc")` returns a
  `RepositoryIngestionService` whose `_repository_id == "repo-abc"`.

All new tests were RED before implementation existed:
`ModuleNotFoundError: No module named
'git_it.repository_ingestion.application.refresh_all_service'` for the service tests, and
`ImportError: cannot import name 'build_refresh_all_service'` for the composition tests —
then GREEN after each corresponding implementation step, per this project's TDD
discipline.

Full suite: **1150 passed, 33 skipped** (was 1142 passed / 33 skipped before this batch;
+8 new tests, no regressions).

### Gotchas

- Import ordering: `refresh_all_service` sorts alphabetically after the `ports` import
  block (not before it) in `composition.py` — `ruff check` initially caught the wrong
  order.
- `ruff format --check .` initially flagged only the new test file's wrapping
  (`_failed_result`'s signature); `ruff format` applied in place, no functional change.
  Both `ruff check .` and `ruff format --check .` also print an unrelated `Acceso
  denegado (os error 5)` warning while walking `.claude/worktrees/` (a parallel agent's
  worktree) and `tmp/pytest-of-*` — pre-existing, unrelated to this batch's files, and
  every check still reports `All checks passed!` / `... files already formatted`.
- `tests/unit/test_api_static.py` showed as modified in `git status` with no functional
  diff (pre-existing line-ending noise per this batch's brief) — left untouched and
  unstaged.
- Confirmed no CLI/API/static files were touched — this batch is scoped strictly to the
  application service and its composition factory, per spec 028's build order (refresh-all
  service → CLI command → API endpoint → dashboard button).

### Commits

- (not committed by this batch — orchestrator/human will review and commit)
