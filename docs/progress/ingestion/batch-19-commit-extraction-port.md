## Batch 19 — Commit extraction port + service wires extractor

### Goal

Establish the commit extraction contract so the service can receive and count raw commits after a successful clone/fetch, without coupling the application layer to GitPython or any concrete implementation.

### Source of truth

- `docs/specs/001-repository-ingestion.md` commit evidence requirements (section 8)
- Clean architecture boundary: domain holds the data record, application holds the port protocol

### Examples

Service wired with a fake extractor returning 3 commits:

```text
result.commits_extracted == 3
```

Service with no extractor:

```text
result.commits_extracted is None
```

Gateway failure does not trigger extraction:

```text
extractor.call_count == 0
```

CLI success with count:

```text
Ingestion status: CLONING_OR_FETCHING
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Commits: 3 extracted
Run ID: run-abc123
```

### Tests

Added service tests:

- `test_ingestion_service_extracts_commits_after_successful_clone_or_fetch` — extractor is called once and its count is set on the result.
- `test_ingestion_service_skips_extraction_when_no_extractor_is_wired` — `commits_extracted` is `None` when no extractor is injected.
- `test_ingestion_service_does_not_extract_commits_on_gateway_failure` — extractor is never called on git gateway failure.

Added CLI tests:

- `test_ingest_cli_prints_commit_count_in_success_output_when_present` — `Commits: N extracted` appears when `commits_extracted` is set.
- `test_ingest_cli_omits_commit_count_when_absent` — no `Commits:` line when `commits_extracted` is `None`.

### Production behavior

Added `domain/commits.py` with `ExtractedCommit` (sha, committed_at, message, author_name, committer_name, parent_shas).

Added `CommitExtractor` protocol to `application/ports.py` with `extract_commits() -> list[ExtractedCommit]`.

Updated `IngestionResult` with `commits_extracted: int | None = None`.

Updated `RepositoryIngestionService.__init__` to accept `commit_extractor: CommitExtractor | None = None` and call it after a successful clone/fetch.

Updated `_print_ingestion_result` to print `Commits: N extracted` before the Run ID line when the count is present.

Composition unchanged — extractor remains unwired until a real GitPython implementation exists.

### Follow-up

The next batch can add the GitPython-backed `CommitExtractor` implementation in `infrastructure/`, wire it into composition, and start proving real commit counts against a local fixture repository.
