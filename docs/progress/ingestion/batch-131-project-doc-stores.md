## Batch 131 — README/CHANGELOG persistence stores (spec 025, slice 2)

### Goal

Add the SQLite and PostgreSQL stores for `ProjectDocContent` (spec 025):
`SqliteProjectDocStore` and `PostgresProjectDocStore`, both structurally
satisfying the `ProjectDocReader`/`ProjectDocWriter` Protocols already defined
in `application/ports.py` (batch 130). No service wiring, no
`composition.py` factory, no narrative-prompt integration — those follow in
batches 132/133, matching the spec's locked TDD order (domain → reader →
stores → service wiring → narrative integration).

### Why

Batch 130 shipped `ProjectDocContent` and `GitPythonProjectDocReader`, both
read-only against the bare git clone. Before `RepositoryIngestionService` can
persist captured README/CHANGELOG content (batch 132) or `NarrativeService`
can read it back for prompt injection (batch 133), a durable store is
needed for both supported backends.

### What was added

**`infrastructure/sqlite/project_docs.py`** (new) / **`infrastructure/postgres/project_docs.py`** (new)
- `SqliteProjectDocStore(database_path)` / `PostgresProjectDocStore(conninfo)`
  — one upserted row per `repository_id` in a new `project_docs` table.
  SQLite has its own `initialize()` (`CREATE TABLE IF NOT EXISTS`, mirroring
  `SqliteDefaultBranchStore`); PostgreSQL has no `initialize()` — its schema
  comes from `migrations/001_initial.sql` only, mirroring
  `PostgresDefaultBranchStore` exactly.
- `save_project_docs(content: ProjectDocContent) -> None` — upsert on
  `repository_id` (`ON CONFLICT ... DO UPDATE`).
- `get_project_docs(repository_id: str) -> ProjectDocContent | None` — this
  method name matches the `ProjectDocReader` Protocol exactly (locked in
  batch 130), so both stores structurally satisfy `ProjectDocReader`
  alongside `GitPythonProjectDocReader`. Returns `None` when no row exists.
  Truncation flags are stored as `INTEGER` (0/1) and converted back to real
  Python `bool` on read (`bool(row[...])`), matching the domain field's
  `bool` type exactly rather than leaking the storage representation.
- **File placement**: given a new, dedicated module — not added to
  `infrastructure/sqlite/github.py` / `infrastructure/postgres/github.py`
  (where `SqliteDefaultBranchStore`/`PostgresDefaultBranchStore` live).
  `default_branch_metadata`'s store landed in `github.py` for file-layout
  reasons at the time it was built, even though its own capture mechanism is
  git-based, not GitHub-API-based. Project-doc content has nothing to do
  with GitHub's API either, so rather than compounding that same
  file-layout mismatch, it gets its own `project_docs.py` module in both
  packages — mirroring the same reasoning batch 130 already used for
  `GitPythonProjectDocReader`'s own dedicated
  `infrastructure/project_docs.py` module.
- **`captured_at` column type**: stored as `TEXT NOT NULL` (isoformat string,
  round-tripped via `datetime.fromisoformat`) on both backends, not
  `TIMESTAMPTZ`. The spec's Domain Concepts section proposed
  `TIMESTAMPTZ NOT NULL DEFAULT NOW()` by analogy with `updated_at` columns
  elsewhere in the migration — but every existing `TIMESTAMPTZ ... DEFAULT
  NOW()` column in this schema (`repo_metadata.updated_at`,
  `default_branch_metadata.updated_at`) is exclusively DB-generated; none of
  them round-trip a Python-supplied point-in-time value. `captured_at` is
  supplied by the caller (`GitPythonProjectDocReader`'s
  `datetime.now(UTC)`), which is exactly the shape `discussion_evidence
  .generated_at` and `github_context.fetched_at` already use — both `TEXT
  NOT NULL`, written via `.isoformat()`. Matching that established
  convention avoids introducing implicit text-to-timestamptz cast behavior
  for a column this codebase already has a working pattern for.
- **Truncation-flag column type**: `INTEGER NOT NULL DEFAULT 0` on both
  backends (not `BOOLEAN`), matching `github_context.has_github_data` — the
  only existing "boolean-shaped" column in this migration file. No column
  in `migrations/001_initial.sql` currently uses a native `BOOLEAN` type, so
  `INTEGER` 0/1 is the actual established convention, not `BOOLEAN`.

**`migrations/001_initial.sql`** — new `project_docs` table block, placed
immediately after `default_branch_metadata`.

**`infrastructure/sqlite/repository.py` / `infrastructure/postgres/repository.py`**
- `SqliteRepositoryDeleter` / `PostgresRepositoryDeleter` now also delete from
  `project_docs` (added to the existing `existing_tables`-gated table list,
  right after `default_branch_metadata`, before `ingestion_runs`).

**Package re-exports** — `SqliteProjectDocStore` / `PostgresProjectDocStore`
added to `infrastructure/sqlite/__init__.py` / `infrastructure/postgres/__init__.py`'s
import lines and `__all__` lists.

### Tests added

- `tests/unit/test_project_doc_store_sqlite.py` (new, 7 tests): absent row →
  `None`; roundtrip with both README + CHANGELOG; upsert overwrites;
  distinct repositories independent; `initialize()` idempotent; README-only
  roundtrips with `changelog_text is None`; truncation flags roundtrip as
  real Python `bool` (not raw `0`/`1` ints).
- `tests/unit/test_postgres_adapters.py` (extended, 3 tests): roundtrip,
  upsert-overwrite, and absent-row for `PostgresProjectDocStore`, gated by
  the existing `DATABASE_URL`-must-start-with-`postgresql` skip marker,
  mirroring the `DefaultBranchStore` section immediately above it.

Full suite: **976 passed, 27 skipped** (up from 969 passed / 24 skipped at
batch 130 — the 7 new SQLite tests now pass, and the 3 new Postgres tests
are skipped locally, same as every other Postgres-gated test without a live
`DATABASE_URL`).

### Gotchas

- No `BOOLEAN`-typed column exists anywhere in `migrations/001_initial.sql`
  today, despite the spec text proposing one — verified by grep before
  writing the migration, rather than guessing from the spec's suggested
  type. `INTEGER NOT NULL DEFAULT 0` (mirroring `has_github_data`) is the
  actual convention.
- Similarly, `captured_at TEXT NOT NULL` (mirroring `generated_at`/
  `fetched_at`) was chosen over the spec's proposed `TIMESTAMPTZ` for the
  same reason: the existing `TIMESTAMPTZ` columns are all DB-defaulted, not
  Python-supplied, so they aren't actually the closest precedent for this
  field.

### Commits

- `feat: add SqliteProjectDocStore and PostgresProjectDocStore (spec 025)`
