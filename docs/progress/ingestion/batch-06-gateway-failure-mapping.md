## Batch 6 — Gateway failure mapping

### Goal

Convert controlled Git gateway failures into safe ingestion results.

### Source of truth

- failure mapping table in `specs/001-repository-ingestion.md`
- security requirement to avoid stack traces and unsafe details in user-facing failures

### Examples

```text
REPOSITORY_NOT_FOUND -> FAILED_FETCH / FETCHING_METADATA / retryable=false
CLONE_TIMEOUT -> FAILED_FETCH / CLONING_OR_FETCHING / retryable=true
```

### Tests

Added service tests using a fake failing gateway.

### Production behavior

Added `GitGatewayError` and service handling that maps gateway error codes through `failure_for_error_code`.

The safe message is:

```text
Repository fetch failed safely before analysis could start.
```

### Follow-up

The next batch should avoid inventing behavior for unknown gateway error codes unless the specification is updated. The current specification defines known error-code mappings but does not define an unknown-code fallback.
