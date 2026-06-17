## Batch 4 — Application validation boundary

### Goal

Introduce the repository ingestion application service without real Git mining.

### Source of truth

- URL contract
- failure mapping
- no network/live repository default test policy

### Examples

Invalid input:

```text
not-a-url -> FAILED_VALIDATION / INVALID_URL / VALIDATING_URL
```

Unsupported host:

```text
https://gitlab.com/owner/repo -> FAILED_VALIDATION / UNSUPPORTED_URL / VALIDATING_URL
```

### Tests

Added service tests proving invalid URLs fail safely and do not call Git tooling.

### Production behavior

Added `RepositoryIngestionService`, `GitGateway` protocol, and `IngestionResult`.

### Follow-up

The service became the stable seam for CLI/query/API layers.
