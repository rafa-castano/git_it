# ADR 010: Accepted Limitations of the Local-First Single-Process MVP

Status: Accepted  
Date: 2026-06-29  
Decision makers: Architecture Agent, Infrastructure and Cloud Agent

## Context

The Git It MVP is deployed as a single-process FastAPI application (`git-it serve` → `uvicorn`)
running on the developer's local machine (see ADR 005 and `.agents/05-infrastructure-cloud-agent.md`).
This architecture enables a no-container, no-cloud setup that works in constrained corporate
environments, but it brings a set of deliberate design choices that would be unacceptable in a
multi-process, multi-tenant, or public deployment.

This ADR records three such choices explicitly, with the code evidence for each and the
conditions under which each must be revisited.

## Decision

Accept the following three limitations for the local-first single-process MVP. Each is a
conscious trade-off, not an oversight.

---

### (a) In-memory progress state for analyze and regen jobs

**What:** Background job progress is tracked in two module-level dictionaries protected by
`threading.Lock`:

```python
# src/git_it/api/routes/repos.py
_analyze_progress: dict[str, dict] = {}
_analyze_progress_lock = threading.Lock()

_regen_progress: dict[str, dict] = {}
_regen_progress_lock = threading.Lock()
```

`_analyze_bg` updates `_analyze_progress[repository_id]` via an `on_progress` callback.
`_regen_bg` updates `_regen_progress[repository_id]` on start and finish.
`GET /api/repos/{id}/analyze/status` and `GET /api/repos/{id}/case-study/regen-status` read
these dicts to report progress to the frontend.

**Accepted limitations:**

- Progress state is lost on server restart. A polling frontend will see `running: False` after a
  restart even if the job was mid-run.
- Only one process can serve accurate progress. Under multiple uvicorn workers or a process
  manager like gunicorn, each worker has its own dict and progress queries may be routed to a
  worker that did not start the job.
- The dicts are not bounded — a very large number of repository IDs would grow memory
  indefinitely, though this is negligible at MVP scale (single developer, few repos).

**Revisit when:** multi-process or multi-worker deployment is introduced. At that point replace
the in-memory dicts with a shared-state store (Redis, database row, or shared memory via a
process manager).

---

### (b) CORS `allow_origins=["*"]` with write endpoints protected by API key

**What:** The FastAPI application (`src/git_it/api/app.py`) configures CORS to accept requests
from any origin, but restricts the allowed methods to `GET` only:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
```

All state-mutating endpoints (`POST /api/repos/ingest`, `POST /api/repos/{id}/analyze`,
`POST /api/repos/{id}/case-study/regenerate`) require a valid API key via the `require_api_key`
dependency (`src/git_it/api/auth.py`).

This means:

- Any origin may read repository lists, commit lists, contributors, patterns, and case studies.
- Write operations require the `X-API-Key` header regardless of origin.
- Cross-site read access is intentionally open for the local-developer use case where the
  frontend (Vite dev server or a separate local port) makes requests to the API.

**Accepted limitations:**

- `allow_origins=["*"]` exposes all GET responses to any web page, including potentially
  sensitive repository metadata or analysis results.
- If write endpoints ever drop the API-key requirement (e.g., for a demo mode), the open
  CORS policy becomes a much wider attack surface.

**Revisit when:** the server is deployed publicly or in any multi-tenant context. At that point,
restrict `allow_origins` to a known list of trusted origins and review the authentication model
end-to-end before any public release.

---

### (c) Direct SQLite reader instantiation in API route handlers

**What:** Several GET route handlers in `src/git_it/api/routes/repos.py` instantiate SQLite
readers directly rather than going through the composition layer:

```python
# list_repos
reader = SqliteRepositoryListReader(db_path)

# get_case_study / regenerate_case_study
store = SqliteCaseStudyStore(db_path)

# estimate_analyze
count_reader = SqliteCommitCountReader(db_path)

# get_commits
reader = SqliteCommitWithAnalysisReader(db_path)

# get_contributors
reader = SqliteContributorReader(db_path)
```

These five readers (`SqliteRepositoryListReader`, `SqliteCaseStudyStore`,
`SqliteCommitCountReader`, `SqliteCommitWithAnalysisReader`, `SqliteContributorReader`) are
constructed with a hard-coded `db_path`, bypassing the `_get_db_backend()` / `build_*`
factory functions in `src/git_it/repository_ingestion/composition.py`.

By contrast, the write/service paths (`build_repository_ingestion_service`,
`build_commit_analysis_service`, `build_narrative_service`, `build_pattern_detection_service`)
in `composition.py` already call `_get_db_backend()` and select either the SQLite or the
PostgreSQL adapter at runtime based on the `DATABASE_URL` environment variable.

This means that when `DATABASE_URL` points to a PostgreSQL instance, the write paths use
Postgres but the five read endpoints above still read from SQLite — producing incorrect
(empty or stale) responses.

**Accepted limitations:**

- PostgreSQL is not a fully supported runtime for the API read layer. The
  `DATABASE_URL=postgresql://...` path works only for the CLI-driven write pipeline, not for
  the API's list/read endpoints.
- Any API-level query test that exercises the read endpoints assumes SQLite.

**Revisit when:** PostgreSQL needs to be a first-class runtime target for the API read layer.
At that point, wrap these five readers in `build_*` factories inside `composition.py` that
honour `_get_db_backend()`, and update the route handlers to call the factories (passing
`project_root`) instead of constructing `Sqlite*` classes directly.

## Consequences

### Positive

- Zero infrastructure overhead for the local developer: no Redis, no shared DB, no config.
- CORS open-GET policy allows the local Vite dev server to call the API without proxy config.
- Direct SQLite readers are simpler and faster to introduce for read-only endpoints; no
  composition-layer boilerplate required.

### Negative

- Progress state is fragile across restarts and invisible across workers.
- CORS policy is permissive by default and requires explicit hardening before public use.
- Postgres support for the API read layer requires non-trivial refactoring of five route handlers.

### Neutral

- All three limitations are documented here so they are not mistaken for design oversights when
  revisited.
- The composition layer (`composition.py`) already provides the pattern for backend-agnostic
  factory functions — extending it to cover the read endpoints is mechanical work.

## Alternatives considered

**Persistent progress store (Redis or DB rows):** Correct for multi-process deployments but
adds a required external service. Rejected for the MVP to stay within the local-first,
no-daemon constraint of ADR 005.

**Restrictive CORS from day one:** Would require maintaining an origin allowlist that changes
with each developer's local port. Rejected for the MVP because the API is not publicly exposed
and write endpoints are already API-key-protected.

**Route handlers call `build_*` factories:** The right long-term approach, but requires the
factories to return named read-only query objects, not just service objects. Deferred until
Postgres read support is a real requirement.

## Security impact

- (a) No security impact — in-memory dicts hold only numeric progress counters, not user data.
- (b) The open CORS policy combined with API-key-protected writes is the accepted posture for a
  local-first tool. MUST be hardened before any public or multi-tenant deployment.
- (c) No security impact — readers are read-only. The concern is correctness (wrong backend),
  not confidentiality.

## Quality impact

- (a) `tests/unit/test_api_analyze.py` and `tests/unit/test_api_repos.py` cover the progress
  endpoints; they do not test restart-survival or multi-worker consistency.
- (b) `tests/unit/test_api_repos.py` and `tests/unit/test_api_analyze.py` cover API-key
  enforcement; CORS policy is not covered by automated tests.
- (c) No test currently exercises the API read endpoints against a PostgreSQL backend; tests
  assume SQLite throughout.

## Documentation impact

- `.agents/05-infrastructure-cloud-agent.md` — local-first MVP principle this ADR implements.
- `ADR/005-use-local-first-no-container-mvp.md` — the parent infrastructure decision.
- `ADR/006-use-postgresql-pgvector.md` — PostgreSQL adapter scope and limitations.
- `docs/progress/infrastructure/batch-63-postgresql-migration.md` — Postgres adapter
  implementation scope (write/service paths only).

## Links

- `.agents/05-infrastructure-cloud-agent.md`
- `ADR/005-use-local-first-no-container-mvp.md`
- `ADR/006-use-postgresql-pgvector.md`
- `src/git_it/api/routes/repos.py` — limitations (a) and (c)
- `src/git_it/api/app.py` — limitation (b)
- `src/git_it/repository_ingestion/composition.py` — `_get_db_backend()` and `build_*` factories
