## Batch 5 — Valid URL starts clone/fetch lifecycle

### Goal

Make valid repository inputs cross the application boundary into the Git gateway using canonical URLs.

### Source of truth

- URL contract
- ingestion lifecycle stages from `docs/specs/001-repository-ingestion.md`

### Examples

Both inputs call the gateway with the same canonical URL:

```text
https://github.com/owner/repo
https://github.com/owner/repo.git

=> https://github.com/owner/repo
```

### Tests

Added service tests for valid URL and `.git` suffix normalization.

### Production behavior

`RepositoryIngestionService.ingest` now calls `GitGateway.clone_or_fetch(canonical_url)` and returns `CLONING_OR_FETCHING` for the current lifecycle boundary.

### Follow-up

Future batches should replace the spy gateway with a safe local Git adapter contract, still without executing repository code.
