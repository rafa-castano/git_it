## Batch 2 — Failure mapping

### Goal

Centralize ingestion failure status, error code, stage, and retryability rules.

### Source of truth

- `docs/specs/001-repository-ingestion.md` failure mapping table

### Examples

```text
INVALID_URL -> FAILED_VALIDATION / VALIDATING_URL / retryable=false
REPOSITORY_NOT_FOUND -> FAILED_FETCH / FETCHING_METADATA / retryable=false
CLONE_TIMEOUT -> FAILED_FETCH / CLONING_OR_FETCHING / retryable=true
STORAGE_FAILED -> FAILED_PERSISTENCE / PERSISTING_FACTS / retryable=true
```

Dynamic examples require a caller-provided stage:

```text
LIMIT_EXCEEDED
INGESTION_TIMEOUT
CANCELLED_BY_USER
```

### Tests

Added unit tests for static mappings, dynamic mappings, missing dynamic stage, and unknown codes.

### Production behavior

Added `IngestionFailure` and `failure_for_error_code`.

### Follow-up

Application services should delegate failure classification to this mapper instead of duplicating status logic.
