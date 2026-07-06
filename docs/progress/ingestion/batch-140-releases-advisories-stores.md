## Batch 140 — Release/Advisory evidence persistence stores (spec 026, slice 4)

### Goal

Add the four persistence stores for spec 026's evidence models:
`SqliteReleaseEvidenceStore`, `PostgresReleaseEvidenceStore`,
`SqliteAdvisoryEvidenceStore`, `PostgresAdvisoryEvidenceStore`. This is the
fourth spec-026 build slice — batch 137 shipped the domain models, batch 138
the REST fetchers, batch 139 the LLM summarizers. Ingest-time wiring and
narrative-prompt integration remain for later batches (domain → fetchers →
summarizers → stores → wiring → narrative), matching the spec's locked TDD
order.

### Why

`ReleaseEvidence` and `AdvisoryEvidence` (batch 137) are schema-validated LLM
summarizer output (batch 139) with nowhere to live yet. Before
`RepositoryIngestionService` can persist them at ingest time (batch 141) or
`NarrativeService` can read them back for prompt injection (batch 142), a
durable store is needed for both supported backends — mirroring exactly how
`SqliteDiscussionEvidenceStore` / `PostgresDiscussionEvidenceStore` (spec 022)
already persist the structurally identical `DiscussionEvidence` shape.

### What was added

**`infrastructure/sqlite/releases.py`** (new) / **`infrastructure/postgres/releases.py`** (new)
- `SqliteReleaseEvidenceStore(database_path)` / `PostgresReleaseEvidenceStore(conninfo)`
  — one upserted row per `(repository_id, tag_name)` in a new
  `release_evidence` table. SQLite has its own `initialize()`
  (`CREATE TABLE IF NOT EXISTS`); PostgreSQL has no `initialize()` — its
  schema comes from `migrations/001_initial.sql` only, mirroring
  `PostgresDiscussionEvidenceStore` exactly.
- `save_release_evidence(repository_id, items: list[ReleaseEvidence]) -> None`
  — upsert on `(repository_id, tag_name)` (`ON CONFLICT ... DO UPDATE`).
- `get_release_evidence(repository_id: str) -> list[ReleaseEvidence]` —
  reconstructs `ReleaseEvidence` from stored rows; `claim_type` round-trips
  via `str(row[...])  # type: ignore[arg-type]` (str→Literal, same pattern
  `DiscussionEvidence.claim_type` already uses).

**`infrastructure/sqlite/advisories.py`** (new) / **`infrastructure/postgres/advisories.py`** (new)
- The symmetric pair for `AdvisoryEvidence`, keyed on
  `(repository_id, ghsa_id)` in a new `advisory_evidence` table. Same
  `initialize()`/no-`initialize()` split. `severity` round-trips via the same
  `str(row[...])  # type: ignore[arg-type]` pattern as `claim_type` above.
- `save_advisory_evidence(repository_id, items: list[AdvisoryEvidence]) -> None`
  / `get_advisory_evidence(repository_id: str) -> list[AdvisoryEvidence]`.

**`migrations/001_initial.sql`** — new `release_evidence` and
`advisory_evidence` table blocks, placed immediately after
`discussion_evidence` (the closest structural analog). `confidence` is
`DOUBLE PRECISION NOT NULL` and `generated_at` is `TEXT NOT NULL` on both new
tables — copied verbatim from `discussion_evidence`'s existing column types,
not re-derived from the spec's Domain Concepts section, so a Python-supplied
`datetime.isoformat()` value round-trips the same way it already does for
discussion evidence.

**`infrastructure/sqlite/repository.py` / `infrastructure/postgres/repository.py`**
- `SqliteRepositoryDeleter` / `PostgresRepositoryDeleter` now also delete from
  `release_evidence` and `advisory_evidence` (added to the existing
  `existing_tables`-gated table list, right after `project_docs`, before
  `ingestion_runs`).

**Package re-exports** — all four new classes added to
`infrastructure/sqlite/__init__.py` / `infrastructure/postgres/__init__.py`'s
import lines and `__all__` lists.

### Tests added

- `tests/unit/test_release_evidence_store_sqlite.py` (new, 7 tests): absent
  repository → `[]`; roundtrip (including `limitations`/`source_inputs` lists
  and `confidence` float); upsert overwrites on `(repository_id, tag_name)`;
  unknown repository → `[]`; distinct repositories independent;
  `initialize()` idempotent.
- `tests/unit/test_advisory_evidence_store_sqlite.py` (new, 7 tests): the
  symmetric set, keyed on `(repository_id, ghsa_id)`, asserting `severity`
  round-trips.
- `tests/unit/test_postgres_adapters.py` (extended, 6 tests): roundtrip and
  upsert-overwrite for `PostgresReleaseEvidenceStore` and
  `PostgresAdvisoryEvidenceStore` (absent-row case included), gated by the
  existing `DATABASE_URL`-must-start-with-`postgresql` skip marker, mirroring
  the `DiscussionEvidence` section immediately above.

Full suite: **1073 passed, 33 skipped** (up from 1059 passed / 27 skipped
before this batch — the 14 new SQLite tests now pass, and the 6 new Postgres
tests are skipped locally, same as every other Postgres-gated test without a
live `DATABASE_URL`).

### Gotchas

- `discussion_evidence`, not `project_docs`, is the correct column-type
  template for these two tables — `project_docs.captured_at` is `TEXT NOT
  NULL` too but has no `confidence` column at all, so `discussion_evidence`
  (same `claim_type`/`confidence`/`limitations`/`source_inputs`/
  `generated_at`/`model` shape as `ReleaseEvidence`, and same shape minus
  `claim_type`→`severity` for `AdvisoryEvidence`) is the closer analog and
  was used verbatim rather than guessed.
- `SqliteRepositoryDeleter`/`PostgresRepositoryDeleter`'s existing
  `existing_tables` list does **not** currently include
  `discussion_evidence` itself (a pre-existing gap from spec 022, out of
  scope here) — `release_evidence`/`advisory_evidence` were still added
  right after `project_docs` (the last table actually present in the
  deleter's list), keeping dependency order explicit rather than copying the
  gap forward.

### Commits

- `feat: add Release/Advisory evidence stores (SQLite + Postgres) (spec 026)`
