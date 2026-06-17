## Batch 16 — Application ingestion run persistence

### Goal

Wire ingestion run persistence into the application service through an application writer port, without making the service depend on SQLite.

### Source of truth

- `specs/001-repository-ingestion.md` ingestion run audit and failure persistence requirements
- Batch 13 SQLite ingestion run store
- Batch 14 architecture layers
- Batch 15 query DTO/read port

### Examples

Success-like current MVP result:

```text
status=CLONING_OR_FETCHING
run_id=run-1
canonical_url=https://github.com/owner/repo
completed_at=None
```

Validation failure:

```text
status=FAILED_VALIDATION
error_code=UNSUPPORTED_URL
error_stage=VALIDATING_URL
retryable=false
canonical_url=""
```

The empty canonical URL for invalid inputs is intentional: credential-bearing or malformed raw URLs must not be persisted as repository evidence.

Gateway failure:

```text
status=FAILED_FETCH
error_code=CLONE_TIMEOUT
error_stage=CLONING_OR_FETCHING
retryable=true
safe_message=Repository fetch failed safely before analysis could start.
```

### Tests

Added application-service tests with a fake run writer.

Extended composition tests to verify the default factory wires `RepositoryIngestionService` to `SqliteIngestionRunStore` under the controlled ingestion workspace.

The tests assert:

- service results include `run_id` when persistence is enabled,
- success-like results are recorded,
- validation failures are recorded without raw invalid URLs,
- Git gateway failures are recorded with mapped status/error/stage/retryable fields,
- composition stores runs in `.data/git-it/ingestion/git-it.sqlite3`.

### Production behavior

Added to `application/ports.py`:

- `IngestionRunRecord`,
- `IngestionRunWriter`.

Updated `RepositoryIngestionService` to optionally accept:

- `repository_id`,
- `run_writer`,
- `run_id_factory`,
- `clock`.

Updated `SqliteIngestionRunStore` to use the application-owned `IngestionRunRecord`.

Updated composition so the default local service persists ingestion runs to SQLite.

### Follow-up

The next batch can expose persisted run IDs in CLI output or use `RepositoryIngestionQueryService` to read back summaries after ingestion.
