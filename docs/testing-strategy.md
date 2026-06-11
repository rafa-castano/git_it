# Testing Strategy

## Purpose

Testing protects the project from silent regressions in deterministic code and AI-generated behavior.

## Test categories

Default tests must not require network access or live public repositories.

Repository ingestion tests should use deterministic local fixture repositories and golden fact snapshots.

Network-dependent ingestion tests must be optional and explicitly marked as integration/network tests.

### Unit tests

Use for:

- parsers,
- mappers,
- validators,
- pattern detectors,
- confidence calculations,
- evidence builders.

### Integration tests

Use for:

- database persistence,
- worker jobs,
- GitHub adapters,
- git mining,
- MCP adapters.

Repository ingestion integration tests must cover:

- local CLI to application service orchestration,
- human-readable CLI summary output,
- stable CLI JSON output for automation,
- safe non-zero CLI failure output without secrets, raw emails, stack traces, or credential-bearing URLs,
- machine-readable ingestion error codes, stages, retryable flags, and safe messages,
- status/error/stage/retryable mappings matching `specs/001-repository-ingestion.md`, including:
  - `INVALID_URL`,
  - `UNSUPPORTED_URL`,
  - `REPOSITORY_NOT_FOUND`,
  - `REPOSITORY_PRIVATE_OR_INACCESSIBLE`,
  - `METADATA_UNAVAILABLE`,
  - `CLONE_TIMEOUT`,
  - `INGESTION_TIMEOUT`,
  - `LIMIT_EXCEEDED`,
  - `GIT_FETCH_FAILED`,
  - `EXTRACTION_FAILED`,
  - `STORAGE_FAILED`,
  - `CANCELLED_BY_USER`,
- stable query DTOs for ingestion run summaries, repository overviews, refs, commit pages, file changes, and statuses,
- query pagination defaults and maximum page size enforcement,
- query filters for branch ref, tag, author identity, path prefix, since, and until,
- query DTOs that do not expose SQLite rows, ORM models, PyDriller objects, GitHub API responses, or CLI text,
- SQLite-backed fact persistence for the MVP,
- duplicate ingestion idempotency,
- branch/ref membership persistence,
- all-branch ingestion when explicitly enabled,
- disappeared branch handling without historical fact deletion,
- force-push/ref movement evidence preservation,
- Git tag ref metadata persistence,
- downstream analysis gating until ingestion reaches `COMPLETED`,
- degraded metadata when GitHub metadata is temporarily unavailable but clone/fetch succeeds,
- `FAILED_FETCH` when metadata confirms a repository is missing, private, or inaccessible,
- diff truncation metadata for large textual diffs,
- binary file metadata without binary content,
- on-demand full diff reconstruction from the bare clone cache,
- safe bare cache refresh when full diff retrieval needs a missing cache,
- contributor identity source and confidence preservation,
- no raw email persistence,
- HMAC-SHA256 email key fallback when `GIT_IT_IDENTITY_PEPPER` is configured,
- commit signature verification metadata as provenance evidence,
- safe `LIMIT_EXCEEDED` failures for configured limits,
- degraded success limitations that do not mark the ingestion run as failed.

Repository ingestion fixture repositories:

- tiny linear repository with three commits,
- branch and merge repository,
- tag repository with lightweight and annotated tags,
- force-push simulation repository,
- large textual diff repository,
- binary file repository,
- malicious-content repository with prompt-injection-like commit messages and diffs,
- submodule and Git LFS pointer repository that must not fetch extras.

### Golden tests

Use for known repositories or fixture histories where expected analyses are stored.

Golden tests must check:

- repository ingestion fact snapshots,
- branch/ref membership accuracy,
- branch deletion and force-push evidence preservation,
- tag ref metadata accuracy,
- diff truncation and full-diff retrieval behavior,
- contributor identity confidence behavior,
- commit signature verification provenance behavior,
- commit classification,
- pattern detection,
- evidence coverage,
- narrative structure.

### Evaluation tests

Use for LLM behavior.

Evaluate:

- factuality,
- traceability,
- confidence calibration,
- no unsupported claims,
- educational usefulness,
- prompt injection resistance.

### E2E tests

Use for complete learner workflows:

```text
submit repo → ingest → analyze commits → detect patterns → generate narrative → inspect evidence
```

## TDD rule

For new behavior:

1. Write failing test.
2. Run test and confirm failure.
3. Implement minimal code.
4. Run test and confirm pass.
5. Refactor safely.
