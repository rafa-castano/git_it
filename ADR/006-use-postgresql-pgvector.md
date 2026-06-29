# ADR 006: Use SQLite for MVP Facts and PostgreSQL with pgvector for Future Semantic Retrieval

Status: Accepted  
Date: 2026-06-10
Decision makers: TBD

## Context

Git It needs to persist repository ingestion facts such as repositories, ingestion runs, commits, file changes, and branch/ref membership.

Those facts are relational and must support idempotency, traceability, and later commit-level and pattern-level analysis.

The project has also adopted a local-first, no-container MVP strategy. The default contributor path must not require PostgreSQL, Docker, Docker Compose, Kubernetes, cloud services, or privileged local setup.

At the same time, future versions may need semantic retrieval over generated analyses, lessons, narratives, or documentation. That future capability may justify PostgreSQL with pgvector.

## Decision

For the MVP repository ingestion workflow, persist raw ingestion facts in a local SQLite database behind a storage port.

SQLite is the default MVP persistence target because it provides relational constraints, transactions, idempotency support, and local-first contributor ergonomics without requiring a daemon or container.

PostgreSQL remains a planned future adapter for larger deployments or multi-user operation.

Use pgvector with PostgreSQL only when semantic search or embedding-backed retrieval is required. Do not require pgvector for the MVP ingestion path.

Application code must depend on storage ports rather than directly coupling domain logic to SQLite, PostgreSQL, or pgvector-specific APIs.

## Consequences

### Positive

- Keeps the MVP aligned with the local-first, no-container infrastructure decision.
- Preserves relational integrity for ingestion facts without requiring external services.
- Keeps the default contributor setup simple and fast.
- Allows future PostgreSQL and pgvector adoption without forcing it prematurely.
- Encourages clean storage boundaries through ports/adapters.

### Negative

- Requires designing storage interfaces before PostgreSQL is introduced.
- SQLite behavior may differ from PostgreSQL in concurrency, SQL dialect, migrations, and type handling.
- Future migration to PostgreSQL will require deliberate compatibility tests and migration planning.

### Neutral

- SQLite is a local MVP persistence choice, not a rejection of PostgreSQL.
- PostgreSQL with pgvector remains the preferred direction for future semantic retrieval if requirements justify it.
- **pgvector is not yet implemented** (as of 2026-06-29). The PostgreSQL adapter for the write
  and service paths is implemented (`src/git_it/repository_ingestion/composition.py` via
  `_get_db_backend()` and batch-63). The `pgvector` extension and any embedding-backed retrieval
  feature remain future work. This ADR is marked Accepted because the core decision — SQLite for
  MVP + Postgres adapter for larger deployments — is implemented; the pgvector clause is a future
  conditional that is explicitly deferred.

## Alternatives considered

- PostgreSQL with pgvector from the start.
- JSON files for local MVP storage.
- In-memory storage only.
- Separate vector database from the beginning.

## Security impact

- SQLite database files must remain inside the controlled project workspace.
- Repository content stored in SQLite remains untrusted data and must not be executed.
- Future PostgreSQL deployments must use least-privilege credentials and avoid exposing secrets through MCP or logs.
- Embeddings must not include secrets or unsupported claims.

## Quality impact

- MVP tests must run without PostgreSQL, Docker, or external database services.
- Storage behavior must be tested through the storage port.
- SQLite idempotency, uniqueness, and transaction behavior must be covered by tests.
- Future PostgreSQL support must include adapter parity tests against the same behavioral contract.

## Documentation impact

- Update repository ingestion specs to identify SQLite as the MVP fact store.
- Document PostgreSQL and pgvector as future deployment/semantic retrieval options.
- Document migration and adapter expectations before introducing PostgreSQL as a required runtime dependency.
