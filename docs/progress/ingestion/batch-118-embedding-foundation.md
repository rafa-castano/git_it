## Batch 118 — RAG semantic search embedding foundation (spec 023, slice 1)

### Goal

Lay the persistence + domain foundation for spec 023 (RAG-enhanced semantic
search): the `EmbeddedChunk` domain shape, the SQLite/PostgreSQL embedding
stores, the composition factory, and the `EmbeddingClient` port. This is the
first of the spec-023 build slices — no embedding API calls and no retrieval
logic land here; those follow in later batches (LiteLLM client → embedding
service → semantic search service → wiring), matching the TDD order the spec
mandates and mirroring how spec 022's discussion evidence foundation (batch
107) was built bottom-up.

### Why

Spec 023 is spec-only; nothing was implemented when it was authored (batch
115). Building it bottom-up keeps each slice independently green and
reviewable. The domain model and stores have no external dependencies (no
OpenAI API, no LLM), so they are the safest place to start and everything
else builds on them.

### What was added

**`domain/embeddings.py`** (new)
- `EmbeddedChunk` — frozen dataclass (not Pydantic — an internal,
  backend-agnostic persistence shape, not an LLM-output-validation boundary).
  Fields: `repository_id`, `source_type: Literal["commit_analysis",
  "discussion_evidence"]`, `source_id`, `text`, `vector: list[float]`,
  `model`, `created_at`.

**`infrastructure/sqlite/embeddings.py`** + **`infrastructure/postgres/embeddings.py`** (new)
- `SqliteEmbeddingStore` / `PostgresEmbeddingStore`: one row per
  `(repository_id, source_type, source_id)`, upserted (`ON CONFLICT ... DO
  UPDATE`). `initialize()` / `save_embeddings()` / `get_all_embeddings()`.
  The vector is stored as a JSON-encoded array in a plain `TEXT` column
  (`vector_json`) — deliberately not a Postgres-specific `vector` column
  type, so both backends share the identical schema and the identical
  in-process similarity-scan code path (no pgvector, per spec 023's
  non-goals and ADR 006's deferral).
- Re-exported from each package's `__init__.py` facade (zero import-site
  churn).

**`migrations/001_initial.sql`** — new `embedding_vectors` table (Postgres path).

**`application/ports.py`** — new `EmbeddingClient` Protocol
(`embed(text: str) -> list[float]`), mirroring `LLMClient`'s minimalism.

**`composition.py`** — new `build_embedding_store(*, project_root)` factory,
backend-aware via `_get_db_backend()` (mirrors `build_discussion_evidence_store`);
calls `.initialize()` on the SQLite path.

### Tests added

- `tests/unit/test_embeddings_domain.py` (2 tests): `EmbeddedChunk`
  constructs with each `source_type` literal value.
- `tests/unit/test_embedding_store_sqlite.py` (7 tests): empty-when-absent;
  save/get roundtrip; upsert overwrites same
  `(repository_id, source_type, source_id)`; unknown repo → `[]`; distinct
  repositories independent; `initialize()` idempotent; distinct
  `source_type` values with the same `source_id` coexist (proves the
  primary key's extra dimension over the discussion evidence store).
- `tests/unit/test_postgres_adapters.py` (extended, +3, `skipif` unless a
  PostgreSQL `DATABASE_URL`): empty-when-absent, roundtrip, upsert overwrites.

Full suite: **909 passed, 24 skipped** (was 900 passed / 21 skipped before
this batch; +9 passing domain/sqlite tests, +3 skipped Postgres tests).

### Gotchas

- The primary key includes `source_type` (unlike discussion evidence's
  two-column key), because a commit's `commit_sha` and a discussion's
  `discussion_id` could coincidentally collide as strings — tested
  explicitly.
- Nothing here calls an embedding API or performs retrieval yet:
  `EmbeddingClient` has no implementation and the stores have no producer
  other than the tests. Dead code until the client/service/wiring batches
  land — intentional, so each slice stays small and green.

### Commits

- `feat: add embedding domain model and stores (spec 023)`
