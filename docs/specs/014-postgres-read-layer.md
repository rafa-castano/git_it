# Feature Spec: 014 — PostgreSQL Read Layer for the API

Status: Accepted
Owner: TBD
Primary agent: Architecture Agent (supporting: Software Engineering Agent, Quality Agent)
Created: 2026-07-02
Updated: 2026-07-02

## Summary

Make the API read endpoints select their database backend (SQLite or PostgreSQL)
through composition-layer factories that honour `DATABASE_URL`, exactly as the
write/service paths already do via `_get_db_backend()` in
`src/git_it/repository_ingestion/composition.py`. This removes limitation (c) of
ADR 010 ("Direct SQLite reader instantiation in API route handlers").

When `DATABASE_URL` selects PostgreSQL and the database is unreachable, reads
FAIL LOUD with a clear 5xx and a diagnostic message. There is never a silent
fallback to SQLite.

## Problem

ADR 010 limitation (c) documents that several GET route handlers in
`src/git_it/api/routes/repos.py` construct SQLite readers directly with a
hard-coded `db_path`, bypassing the backend selection in `composition.py`:

| Handler | Hardcoded adapter (evidence: `repos.py`) |
|---|---|
| `list_repos` | `SqliteRepositoryListReader` (line ~161) |
| `get_case_study` | `SqliteCaseStudyStore` (line ~192) |
| `get_commits` | `SqliteCommitWithAnalysisReader` (line ~287) |
| `_resolve_canonical_url` (used by analyze) | `SqliteIngestionRunStore` (line ~343) |
| `estimate_analyze` | `SqliteCommitCountReader` (line ~412) |
| `get_contributors` | `SqliteContributorReader` (line ~474) |
| `delete_repo` | `SqliteIngestionRunStore` (line ~603), `SqliteRepositoryDeleter` (line ~626) |

The write paths (`build_repository_ingestion_service`,
`build_commit_analysis_service`, `build_narrative_service`,
`build_pattern_detection_service`) already select SQLite or PostgreSQL at
runtime via `_get_db_backend()`. The result: with
`DATABASE_URL=postgresql://...`, writes go to Postgres while the endpoints
above still read from (and delete from) SQLite — producing empty or stale
responses and, for delete, silently removing nothing.

## Goals

1. Add read-side factory functions to `composition.py` — one per hardcoded
   adapter listed above — that follow the existing `_get_db_backend()` pattern
   and return the SQLite or PostgreSQL adapter.
2. Rewire every handler in `repos.py` listed above to call its factory instead
   of constructing a `Sqlite*` class directly.
3. Fail loud: when the Postgres backend is selected and unreachable, the
   endpoint returns a 5xx with a diagnostic message. Never fall back to SQLite.
4. Preserve exact current behaviour when `DATABASE_URL` is unset or non-Postgres
   (default stays SQLite; all existing tests keep passing unchanged).
5. Close the Postgres adapter gaps found while mapping (see Domain concepts —
   Gap analysis) so every rewired read path has a working Postgres counterpart.

## Non-goals

- **No schema changes** — `migrations/001_initial.sql` is untouched.
- **No new endpoints** and no changes to response schemas.
- **No changes to the MCP tools layer** — `src/git_it/tools/registry.py` also
  hardcodes SQLite readers (lines ~97, ~128, ~174, ~188); that is a separate,
  documented follow-up, not covered by ADR 010 limitation (c), which names only
  the API route handlers.
- **No connection pooling** — Postgres adapters keep the existing
  connection-per-operation pattern (`postgres.py` module docstring).
- **No Docker / no live Postgres in default tests** — mirrors the existing
  `tests/unit/test_postgres_adapters.py` skip-when-unset pattern.

## Users

- The developer running Git It against PostgreSQL via `DATABASE_URL`, who today
  gets empty/stale API reads (ADR 010(c)).
- The maintainer who needs backend selection centralized in `composition.py`
  rather than scattered across route handlers.

## User stories

```md
As a developer running Git It with DATABASE_URL=postgresql://...,
I want the API read endpoints to read from the same Postgres database the
write pipeline writes to,
so that the dashboard shows the data I actually ingested and analyzed.
```

```md
As a developer whose Postgres is down or misconfigured,
I want reads to fail with a clear 5xx and a diagnostic message,
so that I never silently read stale data from a leftover SQLite file.
```

## Acceptance criteria

### AC-1 — Read factories in the composition layer
- `composition.py` exposes factory functions for: repository list reader, case
  study store (read use), commit-with-analysis reader, commit count reader,
  contributor reader, ingestion run store (read use), and repository deleter.
- Each factory calls `_get_db_backend()`: it returns the `Postgres*` adapter
  when `DATABASE_URL` starts with `postgresql://` or `postgres://`, otherwise
  the `Sqlite*` adapter built from
  `ingestion_workspace_root(project_root) / "git-it.sqlite3"`.
- Unit tests prove backend selection for every factory by monkeypatching
  `DATABASE_URL` (both directions) and asserting the returned adapter type —
  construction only, no connection, no Docker, no live Postgres.

### AC-2 — Route handlers use the factories
- No `Sqlite*` class is constructed directly in `src/git_it/api/routes/repos.py`;
  the handlers listed in Problem obtain adapters exclusively via the factories.
- The `db_path.exists()` pre-checks apply only to the SQLite backend: with the
  Postgres backend selected, a missing SQLite file must not short-circuit the
  request (a helper in `composition.py` answers "is the database provisioned"
  per backend; for Postgres the answer is always yes — reachability is
  validated by the connection itself, per AC-3).
- With `DATABASE_URL` unset, every existing endpoint test passes unchanged
  (behaviour identical to today, including 404s for missing DB files).

### AC-3 — Fail loud on Postgres connection failure
- With `DATABASE_URL` set to an unreachable Postgres (e.g.
  `postgresql://u:p@127.0.0.1:9/db?connect_timeout=1`), each rewired endpoint
  returns HTTP 503 with a JSON `detail` that names the database backend and
  says it is unavailable — without leaking the connection string, credentials,
  or a raw stack trace.
- The same scenario must NOT return a 200 built from SQLite data — a regression
  test asserts the 5xx even when a valid SQLite file exists on disk.
- Implemented once (an app-level `psycopg.OperationalError` handler), not
  per-handler try/except.

### AC-4 — Postgres adapter parity for the rewired reads
- `PostgresCaseStudyStore.list_available_audiences(repository_id)` exists and
  matches the SQLite contract (`sqlite.py` line ~604).
- `PostgresCommitWithAnalysisReader.count_commits_with_analyses(repository_id,
  *, category=None)` exists and matches the SQLite contract (line ~719).
- `PostgresCommitWithAnalysisReader.list_commits_with_analyses` accepts
  `category: str | None = None` and returns `files_changed` populated from
  `file_facts`, matching the SQLite contract (line ~752).
- `PostgresRepositoryDeleter.delete_repository(repository_id)` exists and
  deletes the repository's rows from the same table set as
  `SqliteRepositoryDeleter` (line ~1088).
- Contract tests for these live in `tests/unit/test_postgres_adapters.py`,
  following its existing pattern: skipped unless `DATABASE_URL` points at a
  real PostgreSQL instance.

## Domain concepts

| Concept | Definition |
|---|---|
| Read factory | A `build_*` function in `composition.py` that returns a read-side adapter for the backend selected by `_get_db_backend()` |
| Backend selection | `DATABASE_URL` starting with `postgresql://` or `postgres://` selects Postgres; anything else (including unset) selects SQLite |
| Fail loud | A Postgres connection failure surfaces as a 503 with a diagnostic message; SQLite is never consulted as a fallback |
| Database provisioned check | Backend-aware replacement for the `db_path.exists()` guard: file existence for SQLite, always-true for Postgres |

### Gap analysis (verified against `postgres.py` as of this spec)

| Needed by rewired handler | Postgres counterpart | Status |
|---|---|---|
| `list_repositories()` | `PostgresRepositoryListReader` (line ~562) | Exists |
| `get_case_study` / `get_repo_context` | `PostgresCaseStudyStore` (line ~498) | Exists |
| `list_available_audiences()` | — | **Gap — implement** |
| `count_commits()` / `count_analyses()` | `PostgresCommitCountReader` (line ~603) | Exists |
| `list_commits_with_analyses(category=...)` + `files_changed` | `PostgresCommitWithAnalysisReader` (line ~629) lacks `category` and `files_changed` | **Gap — implement** |
| `count_commits_with_analyses()` | — | **Gap — implement** |
| `list_contributors()` | `PostgresContributorReader` (line ~672) | Exists |
| `list_ingestion_runs_for_repository()` | `PostgresIngestionRunStore` (line ~98) | Exists |
| `delete_repository()` | — | **Gap — implement `PostgresRepositoryDeleter`** |

## Inputs and outputs

No request or response schema changes. New failure output only:

```json
HTTP 503
{ "detail": "Database unavailable: the PostgreSQL backend selected via DATABASE_URL could not be reached." }
```

## Evidence requirements

- ADR 010 (`docs/adr/010-local-first-mvp-accepted-limitations.md`), limitation (c) —
  the documented debt this spec repays.
- `src/git_it/api/routes/repos.py` — hardcoded adapters (lines cited in Problem).
- `src/git_it/repository_ingestion/composition.py` — `_get_db_backend()` and the
  factory pattern to follow.
- `src/git_it/repository_ingestion/infrastructure/postgres.py` — existing
  Postgres adapters and the gaps listed above.

## Failure modes

| Mode | Behaviour |
|---|---|
| `DATABASE_URL` unset / non-Postgres | SQLite, exactly as today (including `db_path.exists()` 404/empty semantics) |
| Postgres selected, database reachable | Reads served from Postgres |
| Postgres selected, connection fails | 503 with diagnostic `detail`; no SQLite fallback; raw error logged server-side only |
| Postgres selected, SQLite file also present | Postgres wins; the SQLite file is ignored by reads |
| Postgres selected, tables missing | Not masked: the underlying `psycopg` error propagates as a server error (migrations are the write pipeline's responsibility, unchanged) |

## Security considerations

- The 503 diagnostic must not include the connection string — `DATABASE_URL`
  may embed credentials. The message is static; the exception is logged
  server-side (type name only, matching the existing logging style in
  `repos.py`).
- Read-only surface unchanged; `delete_repo` keeps its API-key requirement and
  in-progress guards. No new write capability is introduced.

## Privacy considerations

None beyond current behaviour — the same data is read, from a different backend.

## Observability

Postgres connection failures are logged via the existing module logger pattern
(exception type name, no secrets) when the app-level handler converts them to
503 responses.

## Tests required

| Test | Location |
|---|---|
| Each read factory returns the SQLite adapter when `DATABASE_URL` is unset | `tests/unit/test_read_factories.py` (new) |
| Each read factory returns the Postgres adapter when `DATABASE_URL` is `postgresql://...` | same |
| Database-provisioned helper: file semantics for SQLite, always-true for Postgres | same |
| Every rewired endpoint returns 503 (not 200-from-SQLite) with diagnostic detail when Postgres is selected but unreachable | same |
| 503 detail does not leak the connection string | same |
| `PostgresCaseStudyStore.list_available_audiences` contract | `tests/unit/test_postgres_adapters.py` (skipped without live Postgres, existing pattern) |
| `PostgresCommitWithAnalysisReader` count/category/files_changed contract | same |
| `PostgresRepositoryDeleter` removes all repository rows | same |
| All existing endpoint tests pass unchanged with `DATABASE_URL` unset | existing suites |

All production code follows TDD: failing test first.

## Evaluation required

- Manual: run `git-it serve` with `DATABASE_URL` pointing at a real Postgres
  populated by the CLI pipeline; confirm the dashboard lists repos, commits,
  contributors, and case studies from Postgres. Stop Postgres; confirm reads
  return 503 with the diagnostic message.

## Documentation impact

- `docs/specs/014-postgres-read-layer.md` (this file).
- `docs/adr/010-local-first-mvp-accepted-limitations.md` — dated note marking
  limitation (c) resolved by this spec (history preserved, not rewritten).
- `docs/progress/api/batch-82-postgres-read-layer.md` + entry in
  `docs/progress/README.md`.

## ADR impact

No new ADR: this implements the "Revisit when" clause ADR 010 already wrote
for limitation (c) ("wrap these five readers in `build_*` factories inside
`composition.py` that honour `_get_db_backend()`"). ADR 010 gets a resolution
note; ADR 006 (PostgreSQL scope) is unaffected in substance.

## Open questions

1. **Assumption, documented**: `delete_repo` is included even though it is a
   write, because it was hardcoded to SQLite in the same handlers and leaving
   it would make delete silently no-op once its existence check
   (`SqliteIngestionRunStore`) moves to Postgres. Implementing
   `PostgresRepositoryDeleter` follows the neighboring-class pattern and keeps
   the endpoint coherent.
2. **Assumption, documented**: read factories do not run Postgres migrations
   (`postgres_initialize`) — reads should not mutate schema; the write pipeline
   already provisions tables. SQLite branches initialize only where the current
   handler already does (`SqliteCaseStudyStore.initialize()` in
   `get_case_study`), preserving default-backend behaviour exactly.
3. The MCP tools layer (`tools/registry.py`) still hardcodes SQLite readers —
   candidate for a follow-up spec.
