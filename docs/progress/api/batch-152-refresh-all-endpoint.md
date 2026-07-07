## Batch 152 — `POST /api/repos/refresh-all` API endpoint (spec 028, slice 3)

### Goal

Expose `RefreshAllService` (batch 150) on the API surface: a single collection-level
`POST /api/repos/refresh-all` endpoint the dashboard button (batch 153) will call. Slice 3
of spec 028's build order (refresh-all service → CLI command → **API endpoint** →
dashboard button); the dashboard button itself is out of scope here.

### Why

Slice 2 gave operators a CLI command; the API needs the same capability so the dashboard
can offer a one-click "refresh all tracked repos" control without shelling out to the CLI.

### What was added

**`src/git_it/api/schemas.py`**
- `RefreshRepositoryResult` (`repository_id: str`, `canonical_url: str`, `status: str`,
  `new_commits: int`, `error_code: str | None`, `safe_message: str | None`) — the per-repo
  entry, mapped 1:1 from `RepositoryRefreshResult`'s safe fields only.
- `RefreshAllResponse` (`total_repositories: int`, `refreshed_count: int`,
  `failed_count: int`, `total_new_commits: int`, `repositories: list[RefreshRepositoryResult]`)
  — the aggregate response, mirroring `RefreshAllResult`'s totals plus the per-repo list.

**`src/git_it/api/routes/repos.py`**
- `POST /api/repos/refresh-all` — a literal, collection-level path (no `{repository_id}`
  segment), registered directly under `router` (prefix `/api/repos`), placed right after
  `POST /api/repos/ingest` and before `GET /api/repos`. Rate-limited `5/minute` (mirrors
  `ingest_repo`'s limit, since both are write/cost-relevant collection actions), protected
  by `Depends(require_api_key)` (same auth dependency as `ingest_repo`/`trigger_analyze`/
  `delete_repo`).
- Mirrors `list_repos`'s own `database_is_provisioned` gate: with no database yet, returns
  a zeroed `RefreshAllResponse` (`_EMPTY_REFRESH_ALL_RESPONSE`) — a 200, never a 404 or
  error, since refreshing zero repositories is a success. This also naturally covers the
  spec's "nothing to refresh" acceptance scenario without a separate branch, because
  `RefreshAllService.refresh_all()` itself already returns the same zeroed shape
  (`RefreshAllResult.nothing_to_refresh`) when `list_repositories()` is empty — the
  endpoint's DB-not-provisioned short-circuit only avoids calling
  `build_repository_list_reader` against a not-yet-existing sqlite file, consistent with
  `list_repos`'s reasoning.
- Builds the service via `build_refresh_all_service(project_root=project_root)`, calls
  `.refresh_all()` **synchronously**, and maps `RefreshAllResult` →
  `RefreshAllResponse` directly (no raw internal fields beyond the safe ones listed above
  are exposed).

### Sync-vs-background decision (and why)

Kept synchronous, mirroring the batch-147 embedding-backfill POST's precedent rather than
the analyze/regenerate background-thread + progress-dict + status-poll pattern. Per this
batch's brief: refresh is free (no LLM calls, so no budget guardrail applies), and a large
multi-repo refresh is bounded by git-fetch latency rather than LLM billing. Noted in code
comments (mirroring batch 147's documented reasoning) that this could later move to a
background job if fetch latency across many repositories becomes a real problem — kept
synchronous for this slice, no progress-dict plumbing built speculatively.

### Routing safety (and how it's proven)

`POST /api/repos/refresh-all` is registered as a literal one-segment path. Checked every
existing route in `repos.py` for a same-method, same-depth `{repository_id}`-shaped route
that could shadow it: the only one-segment routes are `POST /ingest` (literal, different
method target) and `DELETE /{repository_id}` (different HTTP method). There is no existing
`POST /api/repos/{repository_id}` bare route at all, so no shadowing is structurally
possible for this method+depth combination today. Proven by
`test_refresh_all_route_reaches_refresh_handler_not_a_param_route`, which POSTs to
`/api/repos/refresh-all` with a fake service seeded with non-trivial per-repo data and
asserts the response body has exactly the refresh-all aggregate shape (`total_repositories`
/ `refreshed_count` / `failed_count` / `total_new_commits` / `repositories` keys, with the
seeded values populated) — a shadowing param route would either 404/405 or return an
unrelated shape, not this one.

### Real symbols grounded on

- `RefreshAllService.refresh_all() -> RefreshAllResult` and `RepositoryRefreshResult`
  (`application/refresh_all_service.py`, batch 150) — confirmed field names
  (`repository_id`, `canonical_url`, `status`, `new_commits`, `error_code`, `safe_message`)
  and `RefreshAllResult`'s totals (`total_repositories`, `refreshed_count`, `failed_count`,
  `total_new_commits`) plus its `nothing_to_refresh` property before writing the mapper.
- `build_refresh_all_service(*, project_root: Path) -> RefreshAllService`
  (`composition.py`, batch 150) — confirmed it takes only `project_root`.
- `router` (`APIRouter(prefix="/api/repos", tags=["repos"])`), `require_api_key`
  (`api/auth.py`), `limiter` (`api/limiter.py`, slowapi), `ProjectRoot`
  (`Annotated[Path, Depends(get_project_root)]`), and `database_is_provisioned(*,
  project_root)` (`composition.py`) — all reused unchanged, matching the batch-147
  `get_backfill_embeddings_status` / `trigger_backfill_embeddings` pattern named in this
  batch's brief.

### Tests added

New file `tests/unit/test_api_refresh_all.py` (6 tests), mirroring
`test_api_backfill.py`'s `TestClient` + `create_app(project_root=tmp_path)` +
`monkeypatch.setattr(repos_module, "build_X", ...)` injection technique, with a
`_provision_db(tmp_path)` helper (creates an empty sqlite file at the expected path) so
tests that need the service actually invoked can pass the `database_is_provisioned` gate:

- `test_refresh_all_maps_totals_and_per_repository_results` — a fake service returning a
  `RefreshAllResult` with 2 repos (one completed with new commits, one failed with
  `error_code`/`safe_message`) → 200 with totals and per-repo list correctly mapped.
- `test_refresh_all_with_nothing_to_refresh_returns_200_zeroed` — `RefreshAllResult`
  with `nothing_to_refresh=True` (empty repositories) → 200 with zeroed totals and an
  empty list, not a 404.
- `test_refresh_all_with_database_not_provisioned_returns_200_zeroed` — no sqlite file at
  all (no `_provision_db` call, service not invoked) → 200 zeroed, exercising the
  endpoint's own DB gate rather than the service's empty-list branch.
- `test_refresh_all_requires_auth_when_api_key_set` — `GIT_IT_API_KEY` set, POST without a
  bearer token → 401.
- `test_refresh_all_accepts_valid_auth` — same env var, POST with the correct bearer token
  → not 401.
- `test_refresh_all_route_reaches_refresh_handler_not_a_param_route` — the routing-safety
  proof described above.

RED confirmed first: 5 of 6 failed with `AttributeError: <module
'git_it.api.routes.repos'> has no attribute 'build_refresh_all_service'` (tests that patch
the not-yet-imported symbol) and 1 with `assert 405 == 200` (`test_..._database_not_
provisioned...`, which does not patch the service — the route didn't exist yet, so
FastAPI/Starlette's own "path matches nothing, method not allowed on the closest match"
handling produced 405 rather than the intended DB-gate 200). All 6 GREEN after
implementing the schema classes and the route; one intermediate failure (the mapping test
initially returned zeroed data because the test's `tmp_path` had no sqlite file, so the
endpoint's own `database_is_provisioned` gate short-circuited before reaching the fake
service) was fixed by adding `_provision_db(tmp_path)` calls to the tests that need the
service actually invoked, not by weakening the endpoint's gate.

Full suite: **all green**, see exact gate output below.

### Gotchas

- Did not touch `src/git_it/static/`, `interfaces/cli.py`, `application/`, or
  `composition.py` — the dashboard button is out of scope here (batch 153), the CLI
  command shipped in batch 151, and the service/composition factory shipped in batch 150.
- `tests/unit/test_api_static.py` showed as modified in `git status` with no functional
  diff (pre-existing line-ending noise per this batch's brief) — left untouched.
- The empty-list / nothing-to-refresh acceptance scenario is satisfied by two independent
  layers reaching the same zeroed shape: the endpoint's own `database_is_provisioned` gate
  (no DB file yet) and `RefreshAllService.refresh_all()`'s own empty-list branch (DB exists
  but zero ingested repositories) — both tested separately so a future change to either
  layer can't silently break the "success, not 404" guarantee.

### Commits

(left uncommitted — orchestrator reviews, runs gates, and commits)
