## Batch 15 — Ingestion run query DTOs

### Goal

Add the first stable query DTOs over persisted ingestion runs so future CLI/GUI adapters do not depend on SQLite rows or infrastructure records.

### Source of truth

- `docs/specs/001-repository-ingestion.md` query service DTO requirements
- Batch 13 SQLite ingestion run store
- Batch 14 layered architecture boundaries

### Examples

Status DTO:

```text
get_ingestion_status("run-1") -> IngestionStatusDTO(
  run_id="run-1",
  status="FAILED_FETCH",
  error_code="CLONE_TIMEOUT",
  error_stage="CLONING_OR_FETCHING",
  retryable=true,
  safe_message="Repository fetch failed safely before analysis could start."
)
```

Run summary DTO:

```text
get_ingestion_run_summary("run-1") -> IngestionRunSummaryDTO(
  run_id="run-1",
  repository_id="repo-1",
  canonical_url="https://github.com/owner/repo",
  status="COMPLETED",
  started_at="2026-06-15T10:00:00Z",
  completed_at="2026-06-15T10:01:00Z"
)
```

Unknown run behavior:

```text
get_ingestion_status("missing-run") -> None
get_ingestion_run_summary("missing-run") -> None
```

### Tests

Added application query service tests with a fake reader.

Extended SQLite store tests to prove `SqliteIngestionRunStore` can back the application query service through structural typing.

The tests assert:

- query methods return stable DTO dataclasses,
- missing runs return `None`,
- application query service depends on a reader port/protocol rather than SQLite,
- SQLite store can satisfy that reader port without leaking SQLite rows upward.

### Production behavior

Added `application/query_service.py` with:

- `IngestionRunView` protocol,
- `IngestionRunReader` protocol,
- `IngestionStatusDTO`,
- `IngestionRunSummaryDTO`,
- `RepositoryIngestionQueryService`.

No CLI output changed yet.

### Follow-up

The next batch can either wire this query service into composition or connect `RepositoryIngestionService` to write ingestion run records so query DTOs have real application-generated data.
