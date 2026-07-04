## Batch 107 — GitHub Discussions evidence foundation (spec 022, slice 1)

### Goal

Lay the persistence + domain foundation for spec 022 (GitHub Discussions
ingestion and narrative evidence): the two domain shapes, the SQLite/PostgreSQL
evidence stores, the composition factory, and the reader port. This is the first
of the spec-022 build slices; the GraphQL fetcher, the LLM summarizer, the
narrative integration, and the ingest-time wiring land in later batches
(fetcher → summarizer → narrative → wiring), matching the TDD order the spec
mandates.

### Why

Spec 022 is spec-only; nothing was implemented when it was authored (batch 106).
Building it bottom-up keeps each slice independently green and reviewable. The
domain models and stores have no external dependencies (no GitHub API, no LLM),
so they are the safest place to start and everything else builds on them.

### What was added

**`domain/discussions.py`** (new)
- `Discussion` — frozen dataclass, the raw fetched candidate. **Never persisted
  or serialized**: no code path writes its `title`/`body`/`answer_body` anywhere.
  This is the load-bearing mechanism behind "raw discussion text is never
  rendered" (spec 022, Security considerations).
- `DiscussionEvidence` — Pydantic `BaseModel`, the schema-validated, persisted,
  narrative-facing LLM output (mirrors `CommitAnalysis`). A `field_validator`
  enforces `discussion_url` against
  `^https://github\.com/[^/]+/[^/]+/discussions/\d+$` — the deterministic,
  unit-testable form of CODEX.md's evidence-link requirement. `confidence` is
  bounded `[0.0, 1.0]`; `claim_type` is `Literal["design_rationale", "pain_point"]`.

**`infrastructure/sqlite/discussions.py`** + **`infrastructure/postgres/discussions.py`** (new)
- `SqliteDiscussionEvidenceStore` / `PostgresDiscussionEvidenceStore`: one row
  per `(repository_id, discussion_id)`, upserted (`ON CONFLICT ... DO UPDATE`).
  `initialize()` / `save_discussion_evidence()` / `get_discussion_evidence()`.
  Mirror `SqliteRepoMetadataStore`'s structure and missing-row contract.
- Re-exported from each package's `__init__.py` facade (zero import-site churn).

**`migrations/001_initial.sql`** — new `discussion_evidence` table (Postgres path).

**`application/ports.py`** — new `DiscussionEvidenceReader` Protocol
(`get_discussion_evidence(repository_id) -> list[DiscussionEvidence]`).

**`composition.py`** — new `build_discussion_evidence_store(*, project_root)`
factory, backend-aware via `_get_db_backend()` (mirrors
`build_repo_metadata_store`); calls `.initialize()` on the SQLite path.

### Tests added

- `tests/unit/test_discussions_domain.py` (11 tests): valid construction; rejects
  missing/empty/non-GitHub/wrong-path/non-numeric `discussion_url`; rejects
  out-of-range `confidence`; rejects invalid `claim_type`; defaults `limitations`;
  `Discussion` holds raw fields with no validation.
- `tests/unit/test_discussion_evidence_store_sqlite.py` (7 tests): empty-when-absent;
  save/get roundtrip; limitations + source_inputs roundtrip; upsert overwrites;
  unknown repo → `[]`; distinct repositories independent; `initialize()` idempotent.
- `tests/unit/test_postgres_adapters.py` (extended, +3, `skipif` unless a
  PostgreSQL `DATABASE_URL`): empty-when-absent, roundtrip, upsert overwrites.

Full suite: **831 passed, 21 skipped** (was 813 passed / 18 skipped before this
batch; +18 passing domain/sqlite tests, +3 skipped Postgres tests).

### Gotchas

- The `discussion_url` regex uses `[^/]+` for both owner and repo so it cannot be
  tricked into matching across path boundaries — same posture as
  `_parse_owner_repo` in `infrastructure/github.py`.
- Nothing here fetches or summarizes anything yet: `Discussion` has no producer
  and `DiscussionEvidence` has no writer other than the store in tests. The stores
  are dead code until the fetcher/summarizer/wiring batches land — intentional, so
  each slice stays small and green.

### Commits

- `feat: add discussion evidence domain model and stores (spec 022)`
