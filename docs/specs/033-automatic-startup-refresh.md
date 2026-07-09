# Spec 033: Automatic Silent Background Refresh on Startup

**Status:** Implemented
**Spec number:** 033
**Author:** Rafael Castaño
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: Architecture Agent, Infrastructure Agent, Quality Agent
Created: 2026-07-09
Updated: 2026-07-09

## 1. Summary

"Refresh all" (spec 028) re-fetches every tracked repository's commit corpus and, since
spec 030, does so **incrementally** — a repository with no new commits costs almost
nothing. Today it is triggered **manually** by a home-view button that POSTs to
`/api/repos/refresh-all` synchronously and shows a summary.

This spec makes the refresh **automatic and invisible**: once per server process, at
startup, the app spawns a **background daemon thread** that runs the existing
`RefreshAllService.refresh_all()` a single time. It never blocks startup or request
handling, never surfaces anything in the UI, and is failure-isolated. The manual
"Refresh all" **button is removed** — the only observable effect of the auto-refresh is
that the tracked-repository **commit counts** shown on the home view reflect any newly
fetched commits on the next page load. The `/api/repos/refresh-all` HTTP endpoint is
**kept** as a programmatic action (no UI surface), so spec 028's API contract and its
tests are unchanged.

This is feasible now precisely because of spec 030: without incremental extraction, a
per-startup full refresh would re-`git diff` the entire history of every repository on
every launch.

## 2. Problem

Fresh commit data requires the user to remember to click "Refresh all". A user who just
launched the tool sees stale counts until they act. The refresh is already cheap
(incremental, free — no LLM calls), so requiring a manual click is friction with no
benefit.

## 3. Goals

- On server **startup**, run `refresh_all()` exactly **once**, in a background daemon
  thread, without blocking startup or any request (user condition: must not slow page
  load).
- Keep it **fully silent**: no toast, no "refreshing" indicator, no UI element. The only
  visible change is updated commit counts on the next home-view load.
- **Remove** the manual "Refresh all" button and its client handler from the home view.
- **Failure-isolated**: any error is caught and logged by exception **type name only**
  (never a token/URL/message); startup and serving always continue.
- **Single-flight**: never run two overlapping auto-refreshes in one process.
- **Test-safe**: the auto-refresh is **opt-in** (`create_app(enable_startup_refresh=True)`),
  enabled only on the served module-level app. Existing tests build apps with an explicit
  `project_root` and default `enable_startup_refresh=False`, so the suite never spawns a
  refresh thread.

## 4. Non-goals

- **No change to `RefreshAllService`** (spec 028) or the incremental ingest primitive
  (spec 030). This spec only adds a startup trigger and removes a UI button.
- **No periodic/scheduled refresh.** Once per process start — not an interval, not a cron.
  Reopening the browser tab while the server keeps running does **not** re-trigger (the
  trigger is server-process startup, per the user's "Option A").
- **No removal of the `POST /api/repos/refresh-all` endpoint.** Only the UI button is
  removed; the endpoint remains a programmatic escape hatch (spec 028 contract preserved).
- **No frontend involvement in triggering.** The trigger lives entirely in the backend;
  the frontend makes no refresh call (backend-only, decision A).
- **No concurrency change** to `refresh_all` itself (stays sequential, spec 028 non-goal).
- **No new persistence, migration, or schema.**

## 5. Users

- A local user who launches Git It (`git-it serve` / `uvicorn`) and wants the home view's
  repository commit counts to already reflect the latest commits, without clicking
  anything and without any loading indicator getting in the way.

## 6. User stories

- As a local user, when I start the app, its tracked repositories are refreshed for me in
  the background, and I only notice because the commit counts are current.
- As a local user, I am never interrupted, delayed, or shown a spinner by this refresh; if
  it fails, nothing breaks and nothing is shown.

## 7. Acceptance criteria

- **AC-01** When the served app starts (startup lifespan) with `enable_startup_refresh=True`,
  a background daemon thread is spawned that runs
  `build_refresh_all_service(project_root).refresh_all()` exactly once.
- **AC-02** The startup handler returns immediately: it spawns the thread and does not
  join/await it, so app readiness and request handling are not blocked by the refresh
  (the refresh runs off the request path).
- **AC-03** With `enable_startup_refresh=False` (the default, and the path every test and
  ad-hoc `create_app` uses), **no** refresh thread is started on startup.
- **AC-04** If the refresh raises, the exception is caught and logged by **type name only**;
  startup and serving continue normally (best-effort, same posture as spec 028's per-repo
  isolation and the `_fetch_and_store_*` enrichment helpers).
- **AC-05** Single-flight: if an auto-refresh is already running in the process, a second
  start request does **not** spawn a second concurrent refresh (it is a no-op).
- **AC-06** If the database is not provisioned (or there are zero tracked repositories),
  the auto-refresh is a no-op — no error, no service work beyond the existing empty-result
  path.
- **AC-07** The home UI renders **no** "Refresh all" button, status element, or client
  handler; no UI element triggers or reports a refresh.
- **AC-08** The background refresh resolves `project_root` the same way request handling
  does: `app.state.project_root` when set, else `GIT_IT_DATA_DIR`, else the current working
  directory (mirroring `deps.get_project_root`).

## 8. Domain concepts

- **Startup refresh**: a one-shot, process-lifetime background execution of the spec-028
  batch refresh, triggered by the ASGI startup lifespan of the served app.
- **Single-flight guard**: a process-level, non-blocking lock ensuring at most one
  auto-refresh runs at a time.

## 9. Inputs and outputs

- **New module** `api/startup.py`:
  - `run_startup_refresh(project_root: Path) -> None`: the synchronous body — skips when
    the database is not provisioned; otherwise builds `RefreshAllService` and calls
    `refresh_all()`; logs an aggregate (counts only) on success; catches and logs any
    exception by type name. Deterministically unit-testable (no threads).
  - `start_background_refresh(project_root: Path) -> threading.Thread | None`: acquires a
    module-level lock **non-blockingly**; if already held, returns `None` (single-flight);
    otherwise spawns a daemon thread running `run_startup_refresh` (releasing the lock in a
    `finally`) and returns it.
- **`create_app` change** (`api/app.py`): add a keyword-only `enable_startup_refresh: bool
  = False`. When `True`, register an ASGI **lifespan** that calls `start_background_refresh`
  with the resolved `project_root` on startup. The module-level served app is created with
  `enable_startup_refresh=True`.
- **Frontend removal** (`static/index.html`, `static/app.js`): delete the `#refresh-all-btn`
  button, the `#refresh-all-status` element, and the `_doRefreshAll` handler.
- **No API/store/migration change.** The `/refresh-all` endpoint stays.

## 10. Evidence requirements

- Not an LLM/interpretation claim. Correctness evidence: the refresh runs off the request
  path (thread), is single-flight, and is failure-isolated — covered by unit tests on
  `run_startup_refresh` / `start_background_refresh` and the lifespan wiring.

## 11. Failure modes

- **Refresh raises / a repo fetch fails** → caught, logged by type name; startup and
  serving continue (AC-04). Per-repo failures are already isolated inside `RefreshAllService`.
- **DB not provisioned / zero repos** → no-op (AC-06).
- **Double startup / re-entrancy** → single-flight guard makes the second call a no-op
  (AC-05).
- **DB contention with page-load reads**: the refresh writes with `INSERT OR IGNORE` while
  page loads read the same SQLite database. This concurrency already occurs today (the
  manual button ran the identical refresh over HTTP while the page was open) with no
  reported locking, and spec 030 keeps per-startup writes minimal when nothing changed.
  WAL/pragma tuning is out of scope for this spec; if contention is later observed it is a
  separate follow-up.

## 12. Security considerations

- No new external surface (the refresh reuses spec 028's already-authorized ingest path).
- No secret exposure: errors are logged by exception **type name only**, never a message
  (which could carry a tokened `git fetch` URL) — same sanitization posture as spec 028 and
  the enrichment helpers. Repository content stays untrusted input (CODEX §7); this spec
  adds no new place where it is trusted.

## 13. Privacy considerations

- None. No new data collected or exposed; the refresh only updates already-tracked
  repositories' local commit facts.

## 14. Observability

- One aggregate **info** log on completion (repositories refreshed/total, new commits,
  failed) — counts only, no PII, no token/URL. One **warning** log (type name only) on
  failure. No per-repository message logging beyond what `RefreshAllService` already emits.

## 15. Tests required

- Unit (`run_startup_refresh`): builds the service and calls `refresh_all` for a provisioned
  DB (AC-01 body); skips building the service when the DB is not provisioned (AC-06);
  swallows a raising service without propagating (AC-04). Deterministic, no threads.
- Unit (`start_background_refresh`): spawns a **daemon** thread that runs the refresh, and
  returns it (join to assert the fake service ran — AC-01/AC-02); is **single-flight** when
  the lock is already held (returns `None`, spawns no working thread — AC-05).
- Unit (lifespan wiring): `create_app(enable_startup_refresh=True)` triggers
  `start_background_refresh` on startup (via `with TestClient(app)`); the default
  `create_app(...)` does **not** (AC-03).
- Unit (frontend removal, `test_api_static_refresh.py` inverted): served `index.html` has no
  `#refresh-all-btn`; served `app.js` has no `_doRefreshAll` (AC-07).
- Endpoint tests (`test_api_refresh_all.py`) remain **unchanged and green** — the endpoint
  is kept.

## 16. Evaluation required

- None (no LLM prompt or output change).

## 17. Documentation impact

- `docs/architecture.md` roadmap: add spec 033 (Implemented on completion); note the manual
  button's removal and that the endpoint is retained.
- `docs/progress/{api}/batch-{N}-automatic-startup-refresh.md` + README index entry.

## 18. ADR impact

- None expected. The startup trigger is a thin composition-time wiring over the existing
  spec-028 service; no new architectural pattern. (If desired, a one-line note in the
  accepted-limitations ADR about "auto-refresh is per-process-start, not periodic" — optional.)

## 19. Open questions

- None blocking. Whether to later add WAL mode or a periodic refresh are explicit non-goals
  here and can be revisited if DB contention or staleness is observed in practice.
