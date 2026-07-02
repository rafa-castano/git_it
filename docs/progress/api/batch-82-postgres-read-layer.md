# Batch 82 — PostgreSQL read layer for the API (spec 014)

## Goal

Remove ADR 010 limitation (c): API read endpoints hardcoded SQLite readers while the
write/service paths already selected their backend via `_get_db_backend()` and
`DATABASE_URL`. After this batch, every read (and the delete) in
`src/git_it/api/routes/repos.py` goes through a composition-layer factory that honours
`DATABASE_URL`, and a Postgres connection failure fails loud with a 503 — never a silent
fallback to SQLite.

## Changes Made

### Composition layer (`src/git_it/repository_ingestion/composition.py`)

- **Seven read-side factories**, each following the existing `_get_db_backend()` pattern:
  `build_repository_list_reader`, `build_case_study_store`, `build_commit_count_reader`,
  `build_commit_with_analysis_reader`, `build_contributor_reader`,
  `build_ingestion_run_store`, `build_repository_deleter`.
- **`database_is_provisioned(*, project_root)`** — backend-aware replacement for the
  route handlers' `db_path.exists()` guard: file existence for SQLite, always-true for
  Postgres (reachability is validated by the connection itself, which fails loud).

### API routes (`src/git_it/api/routes/repos.py`)

- All direct `Sqlite*` constructions replaced with factory calls; the
  `from ...infrastructure.sqlite import ...` block and `_get_db_path` are gone.
- `db_path.exists()` pre-checks replaced with `database_is_provisioned(...)` so a
  missing SQLite file no longer short-circuits requests when Postgres is selected.
- `get_case_study` no longer calls `store.initialize()` — the SQLite branch of
  `build_case_study_store` does it, preserving the previous behaviour.

### App (`src/git_it/api/app.py`)

- App-level `psycopg.OperationalError` exception handler returning
  `503 {"detail": "Database unavailable: the PostgreSQL backend selected via
  DATABASE_URL could not be reached."}` — static message so the connection string
  (which may embed credentials) can never leak; the exception is logged by type name only.

### Postgres adapters (`src/git_it/repository_ingestion/infrastructure/postgres.py`)

Gaps found while mapping the read paths (each mirrors its SQLite neighbour):

- `PostgresCaseStudyStore.list_available_audiences(repository_id)` — was missing;
  `get_case_study` calls it for `available_audiences`.
- `PostgresCommitWithAnalysisReader.count_commits_with_analyses(repository_id,
  category=None)` — was missing (added to SQLite in batch 80, never mirrored).
- `PostgresCommitWithAnalysisReader.list_commits_with_analyses` — gained the
  `category` filter and `files_changed` aggregation (`STRING_AGG` over `file_facts`,
  the Postgres spelling of SQLite's `GROUP_CONCAT`).
- `PostgresRepositoryDeleter` — was missing entirely; without it, `DELETE /api/repos/{id}`
  on a Postgres backend would have verified existence against Postgres and then silently
  deleted nothing from SQLite.

## Files Changed

- `specs/014-postgres-read-layer.md` — new spec (Accepted)
- `src/git_it/repository_ingestion/composition.py` — 7 read factories + provisioned check
- `src/git_it/api/routes/repos.py` — handlers rewired to factories
- `src/git_it/api/app.py` — fail-loud `psycopg.OperationalError` handler
- `src/git_it/repository_ingestion/infrastructure/postgres.py` — parity gaps closed
- `ADR/010-local-first-mvp-accepted-limitations.md` — dated resolution note on limitation (c)
- `tests/unit/test_read_factories.py` — 31 new unit tests (new file)
- `tests/unit/test_postgres_adapters.py` — 4 new contract tests (skipped without live Postgres)
- `docs/progress/api/batch-82-postgres-read-layer.md` — this file
- `docs/progress/README.md` — new entry in API section

## Tests Added

`tests/unit/test_read_factories.py` (31 tests, all run without Docker or Postgres):

1. 7 factories × 3 backend-selection tests (unset → SQLite, `postgresql://` → Postgres,
   non-Postgres URL → SQLite) — parametrized, construction only
2. `database_is_provisioned` × 3 (SQLite without/with file, Postgres backend)
3. 6 fail-loud endpoint tests (`/api/repos`, case-study, commits, analyze/estimate,
   contributors, DELETE) against an unreachable `postgresql://...127.0.0.1:9/...` —
   assert 503, diagnostic detail, and that credentials never appear in the response
4. `test_postgres_backend_never_falls_back_to_existing_sqlite_file` — a seeded SQLite
   file must NOT be served when Postgres is selected (503, not 200)

`tests/unit/test_postgres_adapters.py` (4 tests, skipped unless `DATABASE_URL` points at
a real Postgres, mirroring the file's existing pattern): `list_available_audiences`,
count/list category filter, `files_changed` aggregation, deleter roundtrip.

Total: 692 → 723 passed (8 → 12 skipped).

## Gotchas

- **The delete path had to come along.** ADR 010(c) named five readers, but `delete_repo`
  and `_resolve_canonical_url` also hardcoded SQLite. Once the existence check moves to
  Postgres, a SQLite-only deleter would silently no-op — so `PostgresRepositoryDeleter`
  was implemented rather than left as a documented gap.
- **Read factories do not run migrations.** Unlike the write factories, they never call
  `postgres_initialize` — reads must not mutate schema, and running migrations per GET
  would be a regression. Missing tables surface as raw psycopg errors, documented in the
  spec's failure modes.
- **Fail-loud tests use port 9 (discard) with `connect_timeout=1`** — connection refused
  is immediate and deterministic on localhost; no network, no Docker.
- **`mypy .` has 8 pre-existing errors** in `tests/unit/test_commit_analysis_domain.py`
  (untouched — a separate cleanup); the CI gate is `mypy src/`, which passes clean.
  Two similar pre-existing errors in `test_postgres_adapters.py`
  (`category="feature"` as `str` vs `CommitCategory`) were fixed here since this batch
  already touched that file with the enum-typed pattern.
- **`git stash` is unreliable in this OneDrive-synced working tree** — a stash/pop cycle
  during this batch hit `Permission denied` on file removal and left duplicate stash
  entries (recovered, both dropped). Avoid stashing here; use worktrees or commits.

## Commits

- TBD
