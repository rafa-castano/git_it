## Batch 7 — Known gateway failure coverage

### Goal

Ensure the application service covers every known fetch/Git gateway failure currently defined by the repository ingestion specification.

### Source of truth

- `specs/001-repository-ingestion.md` default failure mapping table

### Examples

```text
REPOSITORY_NOT_FOUND -> FAILED_FETCH / FETCHING_METADATA / retryable=false
REPOSITORY_PRIVATE_OR_INACCESSIBLE -> FAILED_FETCH / FETCHING_METADATA / retryable=false
METADATA_UNAVAILABLE -> FAILED_FETCH / FETCHING_METADATA / retryable=true
CLONE_TIMEOUT -> FAILED_FETCH / CLONING_OR_FETCHING / retryable=true
GIT_FETCH_FAILED -> FAILED_FETCH / CLONING_OR_FETCHING / retryable=true
```

### Tests

Expanded the service-level gateway failure parametrization to include all known fetch/Git failure codes.

This batch did not need production changes because the batch 6 implementation already delegated classification to `failure_for_error_code` instead of hard-coding individual cases. That is GOOD architecture: one mapper, one source of truth.

### Production behavior

No production code changed in this batch.

### Follow-up

Unknown gateway error-code behavior remains intentionally unspecified. Do not add a fallback until the spec defines whether unknown codes should fail fast for developers or become a safe generic failure for users.
