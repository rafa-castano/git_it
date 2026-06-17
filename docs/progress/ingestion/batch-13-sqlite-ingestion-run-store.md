## Batch 13 — SQLite ingestion run store

### Goal

Add the first SQLite-backed persistence port for ingestion run audit records before enriching CLI summaries.

### Source of truth

- `specs/001-repository-ingestion.md` SQLite-backed fact persistence requirement
- `IngestionRun: append-only per ingestion attempt`
- failure persistence requirements for status, error code, stage, retryable flag, and safe message

### Examples

Successful run record:

```text
run_id=run-1
repository_id=repo-1
canonical_url=https://github.com/owner/repo
status=COMPLETED
started_at=2026-06-15T10:00:00Z
completed_at=2026-06-15T10:01:00Z
```

Failure run record:

```text
status=FAILED_FETCH
error_code=CLONE_TIMEOUT
error_stage=CLONING_OR_FETCHING
retryable=true
safe_message=Repository fetch failed safely before analysis could start.
```

Append-only behavior:

```text
repo-1 -> [run-1, run-2]
```

### Tests

Added unit tests using temporary SQLite databases.

The tests assert:

- ingestion run records round-trip through SQLite,
- failure details are persisted and restored,
- multiple runs for the same repository are retained instead of replacing each other,
- store methods return DTO/dataclass records, not SQLite rows.

### Production behavior

Added `storage.py` with:

- `IngestionRunRecord`,
- `SqliteIngestionRunStore`,
- schema initialization for `ingestion_runs`,
- save/get/list methods for ingestion run audit records.

This batch does not yet wire persistence into `RepositoryIngestionService`; it establishes the storage boundary first.

### Follow-up

The next batch can wire ingestion run creation/update into the application service or add a query service DTO over `SqliteIngestionRunStore` for future CLI/GUI summaries.
