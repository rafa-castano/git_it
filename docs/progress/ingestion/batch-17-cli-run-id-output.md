## Batch 17 — CLI run ID output

### Goal

Expose the persisted run ID in CLI output so the result of each ingestion is traceable without parsing SQLite directly.

### Source of truth

- `docs/specs/001-repository-ingestion.md` CLI human-readable output requirements
- Batch 16 `IngestionResult.run_id` already populated by the application service

### Examples

Success-like status with run ID:

```text
Ingestion status: CLONING_OR_FETCHING
Run ID: run-abc123
```

Failure with run ID:

```text
Ingestion failed: INVALID_URL
Run ID: run-abc123
Repository URL must be a public GitHub HTTPS repository URL.
```

No run ID (persistence not wired):

```text
Ingestion status: CLONING_OR_FETCHING
```

### Tests

Added three CLI unit tests:

- `test_ingest_cli_prints_run_id_in_success_output_when_present` — asserts `Run ID: <id>` follows the status line when `run_id` is present.
- `test_ingest_cli_prints_run_id_in_failure_output_when_present` — asserts `Run ID: <id>` appears between the error code line and the safe message for failure statuses.
- `test_ingest_cli_omits_run_id_line_when_run_id_is_absent` — asserts no `Run ID:` line when `run_id` is `None`.

### Production behavior

Updated `_print_ingestion_result` in `interfaces/cli.py` to print `Run ID: <run_id>` after the status/error line when `run_id` is not `None`.

No other modules changed. The `run_id` was already available on `IngestionResult` since Batch 16.

### Follow-up

The next batch can enrich the success output with more spec-required fields (repository, canonical URL, status, counts, limitations) or begin the commit extraction and persistence layer.
