## Batch 18 — CLI success output with repository identity

### Goal

Enrich the CLI success output with repository identity (owner/repo and canonical URL) so the result of each ingestion is traceable without reading persisted records directly.

### Source of truth

- `specs/001-repository-ingestion.md` CLI human-readable output requirements (section 10)
- `ParsedRepositoryUrl.canonical_url` already computed inside the service during URL validation

### Examples

Success output with repository identity:

```text
Ingestion status: CLONING_OR_FETCHING
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Run ID: run-abc123
```

No repository lines when canonical URL is absent (e.g. validation failure path):

```text
Ingestion failed: INVALID_URL
Run ID: run-abc123
Repository URL must be a public GitHub HTTPS repository URL.
```

### Tests

Added service tests:

- `test_ingestion_service_includes_canonical_url_in_success_like_result` — verifies `canonical_url` is set on success-like results.
- `test_ingestion_service_normalizes_canonical_url_by_stripping_git_suffix` — verifies `.git` suffix does not appear in `canonical_url`.
- `test_ingestion_service_canonical_url_is_none_for_validation_failure` — verifies validation failures leave `canonical_url` as `None`.

Added CLI tests:

- `test_ingest_cli_prints_repository_and_canonical_url_in_success_output` — asserts both lines appear when `canonical_url` is present.
- `test_ingest_cli_omits_repository_lines_when_canonical_url_is_absent` — asserts neither line appears when `canonical_url` is `None`.

### Production behavior

Added `canonical_url: str | None = None` to `IngestionResult` in `application/service.py`.

Populated `canonical_url` for both the gateway-failure and success-like paths (where a valid `ParsedRepositoryUrl` is available). Validation failures leave it `None`.

Updated `_print_ingestion_result` in `interfaces/cli.py` to print `Repository: owner/repo` and `Canonical URL: ...` immediately after the status line, only when `canonical_url` is present. `owner/repo` is derived by stripping the `https://github.com/` prefix from the validated canonical URL.

### Follow-up

The next batch can begin the commit extraction and persistence layer, or add counts and limitations to the CLI output once commit extraction is wired.
