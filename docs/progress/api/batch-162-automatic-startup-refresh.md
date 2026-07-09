## Batch 162 — Automatic silent background refresh on startup (spec 033)

### Goal

Stop making the user click "Refresh all". Every tracked repository is now refreshed
automatically, silently, and in the background **once per server process at startup**, so
the home view's commit counts are already current when the user opens the app — with no
button, no spinner, and no interruption. Feasible now only because of spec 030: without
incremental extraction a per-startup full refresh would re-`git diff` the entire history
of every repository on every launch.

### What was added

**Backend (`src/git_it/api/startup.py`, new)**
- `resolve_startup_project_root(explicit)`: mirrors `deps.get_project_root` (explicit →
  `GIT_IT_DATA_DIR` → cwd) for the no-request startup context (AC-08).
- `run_startup_refresh(project_root)`: the synchronous body. Skips entirely when the
  database is not provisioned (AC-06); otherwise builds the spec-028 `RefreshAllService`
  and runs it, logging an aggregate (counts only) on success. Any exception is caught and
  logged by **type name only** (AC-04) — a failed refresh can never crash the server or
  leak a tokened `git fetch` URL.
- `start_background_refresh(project_root)`: acquires a process-level lock **non-blockingly**
  (single-flight, AC-05); if free, spawns a **daemon** thread running `run_startup_refresh`
  (releasing the lock in `finally`) and returns it; if held, returns `None`.

**Wiring (`src/git_it/api/app.py`)**
- `create_app` gains a keyword-only `enable_startup_refresh: bool = False`. When `True`, an
  ASGI **lifespan** calls `start_background_refresh(resolve_startup_project_root(project_root))`
  on startup — non-blocking (spawns the thread and yields immediately). Off by default so
  every test and ad-hoc `create_app` call is unaffected (AC-03).
- The module-level served `app = create_app(enable_startup_refresh=True)` — the **only**
  instance with the auto-refresh enabled. `git-it serve` / `uvicorn git_it.api.app:app` use
  it, and `git-it serve` already sets `GIT_IT_DATA_DIR` before uvicorn starts, so the
  startup resolver finds the right data dir.

**Frontend removal (`static/index.html`, `static/app.js`)**
- Removed the `#refresh-all-btn` button, the `#refresh-all-status` element, and the
  `_doRefreshAll` client handler (AC-07). A short comment marks where they were and points
  to `api/startup.py`.

**Kept**: the `POST /api/repos/refresh-all` endpoint (spec 028) as a programmatic action —
only the UI button is removed, so spec 028's API contract and its tests are unchanged.

### Behavior (spec 033 acceptance criteria)

- **AC-01/AC-02** Startup spawns a daemon thread that runs `refresh_all()` once, off the
  request path — verified: lifespan-enter measured at ~0.015s, server serves immediately.
- **AC-03** Default `create_app(...)` registers no lifespan and starts no thread.
- **AC-04** A raising refresh is swallowed and logged by type name; serving continues.
- **AC-05** Single-flight: a second start while one runs is a no-op.
- **AC-06** DB not provisioned / zero repos → no-op.
- **AC-07** No "Refresh all" button, status element, or handler in the served UI.
- **AC-08** `project_root` resolves as in request handling (explicit → env → cwd).

### Tests added

- `tests/unit/test_startup_refresh.py` (new): `run_startup_refresh` calls/skips/swallows
  (AC-01 body/AC-06/AC-04); `start_background_refresh` spawns a daemon thread and is
  single-flight (AC-01/AC-02/AC-05); `resolve_startup_project_root` precedence (AC-08);
  lifespan wiring fires only when `enable_startup_refresh=True` (AC-01/AC-03).
- `tests/unit/test_api_static_refresh.py` (inverted): asserts the button, status element,
  and `_doRefreshAll` handler are **gone** (AC-07).
- `tests/unit/test_api_refresh_all.py` unchanged and green (endpoint retained).

Additionally verified out-of-band by entering the served module app's lifespan against an
empty data dir: lifespan enters in ~0.015s (non-blocking), the index is served (200), and
the button is absent.

### Production / PostgreSQL (verified backend-agnostic)

The auto-refresh applies to production (PostgreSQL) with **no code change** — it runs
entirely through the existing backend-selecting composition seam:

- `run_startup_refresh` → `build_refresh_all_service` → `build_repository_list_reader` **and**
  `build_repository_ingestion_service`, both of which switch SQLite vs PostgreSQL via
  `_get_db_backend()` (`DATABASE_URL`). No SQLite-only path exists.
- `database_is_provisioned` returns `True` for PostgreSQL (`composition.py:137-140`), so the
  refresh proceeds against Postgres rather than skipping.
- Production is Postgres (`docker-compose.yml` `DATABASE_URL=postgresql://…`) served by a
  **single** uvicorn worker (`Dockerfile` CMD has no `--workers`) → one refresh per container
  start. `resolve_startup_project_root(None)` and `deps.get_project_root` both resolve to the
  process CWD (`/app`) — no `GIT_IT_DATA_DIR` set, `app.state.project_root` unset on the module
  app — so the startup refresh and request handling agree on the git-cache location.
- The SQLite write/read contention note (§11) is **SQLite-only**; PostgreSQL MVCC does not block
  concurrent reads during the refresh's writes.

Two documented production caveats (spec 033 §11, not bugs): a multi-worker/replica deployment
would fan out to one refresh per process (idempotent but redundant — the single-flight guard is
per-process); and the container's git cache is ephemeral (only `pgdata` is volumed), so the
first refresh after a restart re-clones each repo once (spec 030 still avoids re-diffing).

### Gotchas

- The auto-refresh is **opt-in** and enabled on exactly one instance (the module-level
  served app). This is what keeps the ~1240-test suite from spawning a refresh thread on
  every `create_app(project_root=tmp_path)`.
- `app.py` imports the module (`from git_it.api import startup`) and calls
  `startup.start_background_refresh(...)` by attribute, so tests can monkeypatch it on the
  module.
- DB write/read contention with concurrent page loads is already-tolerated behavior (the
  old manual button ran the identical refresh over HTTP while the page was open) and is
  minimal under spec 030; WAL/pragma tuning is out of scope (spec 033 §11).

### Commits

- `feat: automatic silent background refresh on startup (spec 033)`
