# Batch 73 — Rate limit on the analyze estimate endpoint

## Goal

Close a security gap found during the project-wide audit: `GET /api/repos/{repository_id}/analyze/estimate`
was the only cost/DB-touching endpoint without a rate limit and without authentication. An
unauthenticated client could call it in a tight loop, forcing repeated full-database reads. This
batch adds a `20/minute` limit, consistent with the rate-limiting policy already applied to the
write endpoints (`ingest` 5/min, `analyze` 10/min, `regenerate` 5/min).

Recorded as an accepted design point in `ADR/010-local-first-mvp-accepted-limitations.md` (the
CORS/local-first posture) and specified in `specs/007-cost-estimation.md`.

## Changes Made

### TDD — failing test first

**`tests/unit/test_api_analyze.py`**
- Added `test_estimate_analyze_is_rate_limited_at_20_per_minute`. It introspects slowapi's
  `limiter._route_limits` registry, which `@limiter.limit()` populates keyed by the endpoint's
  fully-qualified name (`git_it.api.routes.repos.estimate_analyze`). The test asserts the key is
  registered and carries a `20 per 1 minute` limit.
- Strategy is **introspection, not behavioural hammering**: the module-level `limiter` uses a
  shared in-memory store keyed by client IP (always `testclient` under `TestClient`). Sending 21
  requests would drain the same bucket the other `estimate` tests rely on and make the suite
  order-dependent. The registry check is deterministic and isolated.
- RED verified: undecorated handlers (`list_repos`, `get_contributors`) are absent from
  `_route_limits`, so without the decorator the `key in limiter._route_limits` assertion fails.

### GREEN — minimum implementation

**`src/git_it/api/routes/repos.py`**
- Added `@limiter.limit("20/minute")` to `estimate_analyze`.
- Added `request: Request` as the first parameter (slowapi requires the endpoint to receive the
  `Request`), mirroring `trigger_analyze`. `Request` was already imported from `fastapi`.

## Files Changed

- `src/git_it/api/routes/repos.py` — decorator + `request` parameter on `estimate_analyze`.
- `tests/unit/test_api_analyze.py` — new rate-limit regression test.
- `docs/progress/api/batch-73-rate-limit-estimate-endpoint.md` — this document.
- `docs/progress/README.md` — index entry.

## Tests Added

- `test_estimate_analyze_is_rate_limited_at_20_per_minute` — regression test proving the limit is
  registered for the estimate endpoint.

Full unit suite after the change: **576 passed, 8 skipped**. `ruff check` and `ruff format --check`
clean on the changed files.

## Gotchas

- slowapi does **not** expose limits as a `_limits` attribute on the decorated function (the
  function is replaced by a `sync_wrapper` whose limit lives in its closure). The authoritative,
  testable source is `limiter._route_limits[<fqname>]`, a list of `Limit` objects whose `.limit`
  stringifies to e.g. `20 per 1 minute`.
- The limit check runs in the slowapi wrapper *before* the handler body, so the first 20 calls
  reach the handler (and may 404 on a missing DB) while the 21st returns 429 — the limit is not
  gated behind a successful lookup.
- Pre-existing, out of scope: `mypy src/` reports a `psycopg2` missing-stub note in
  `postgres.py`; unrelated to this batch and not introduced here.
