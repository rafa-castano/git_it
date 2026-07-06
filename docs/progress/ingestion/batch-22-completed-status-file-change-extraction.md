## Batch 22 — COMPLETED status + file change extraction and persistence

### Goal

Fix the final ingestion status from the intermediate `CLONING_OR_FETCHING` to `COMPLETED`, add file-level change extraction per commit using GitPython stats, persist them idempotently in a `file_facts` table, and expose inserted/reused counts in CLI output.

### Source of truth

- `docs/specs/001-repository-ingestion.md` file-level evidence and completion status requirements
- `ExtractedCommit.file_changes` derived from `commit.stats.files` (GitPython)
- `UNIQUE(repository_id, commit_sha, file_path)` idempotency key

### Examples

First ingestion of a repository with 2 commits each touching 1 file:

```text
Ingestion status: COMPLETED
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Commits: 2 inserted, 0 reused
Files: 2 inserted, 0 reused
Run ID: run-abc123
```

Re-ingestion (no new commits):

```text
Commits: 0 inserted, 2 reused
Files: 0 inserted, 2 reused
```

### Tests

New test file `tests/unit/test_file_fact_store.py`:

- `test_sqlite_file_fact_store_inserts_new_file_facts` — 3 file facts across 2 commits → inserted=3, reused=0.
- `test_sqlite_file_fact_store_marks_existing_file_facts_as_reused_on_reingest` — same facts re-saved → inserted=0, reused=2.
- `test_sqlite_file_fact_store_tracks_mixed_insertions_and_reuses` — 1 new file + 1 existing → inserted=1, reused=1.
- `test_sqlite_file_fact_store_treats_same_file_as_independent_across_repositories` — same (sha, path) in two repos → both inserted.
- `test_sqlite_file_fact_store_skips_commits_with_no_file_changes` — empty file_changes → inserted=0, reused=0.

Updated `tests/unit/test_git_commit_extractor.py`:

- `test_git_commit_extractor_populates_file_changes_per_commit` — each fixture commit adds one .txt file; asserts `file_changes` has 1 entry with non-negative insertions/deletions.

Updated `tests/unit/test_repository_ingestion_service.py`:

- All success-path status assertions changed from `"CLONING_OR_FETCHING"` to `"COMPLETED"`.
- `test_ingestion_service_persists_success_like_run_result` — run record now has `status="COMPLETED"` and `completed_at` set (not `None`).
- `test_ingestion_service_persists_file_facts_and_reports_counts` — fake file fact writer returns `(inserted=5, reused=1)`; asserts on result fields.
- `test_ingestion_service_does_not_report_file_counts_without_file_fact_writer` — no writer → `files_inserted is None`, `files_reused is None`.

Updated `tests/unit/test_repository_ingestion_cli.py`:

- All `status="CLONING_OR_FETCHING"` changed to `status="COMPLETED"`.
- `test_ingest_cli_prints_file_count_in_success_output_when_present` — `Files: 7 inserted, 2 reused` in output.
- `test_ingest_cli_omits_file_count_when_absent` — no `Files:` line when both counts are `None`.

Updated `tests/unit/test_repository_ingestion_composition.py`:

- All `status == "CLONING_OR_FETCHING"` changed to `"COMPLETED"`.
- `test_build_repository_ingestion_service_wires_gitpython_extractor_by_default` — also asserts `files_inserted >= 2`.

### Production behavior

Updated `domain/commits.py`:

- Added `ExtractedFileChange` frozen dataclass with `path`, `insertions`, `deletions`.
- Added `file_changes: tuple[ExtractedFileChange, ...] = field(default_factory=tuple)` to `ExtractedCommit`.

Updated `application/ports.py`:

- Added `FileFactWriter` protocol with `save_file_facts(commits, *, repository_id) -> CommitPersistenceResult`.

Updated `application/service.py`:

- `IngestionResult` gains `files_inserted: int | None = None` and `files_reused: int | None = None`.
- `RepositoryIngestionService` accepts `file_fact_writer: FileFactWriter | None = None`.
- Success path status changed to `"COMPLETED"`.
- Success path `completed_at` now set to `self._clock()` instead of `None`.
- After commit persistence, calls `save_file_facts` if writer is wired.

Updated `infrastructure/commits.py`:

- `GitPythonCommitExtractor` extracts file changes via `commit.stats.files` → `ExtractedFileChange` tuples.
- `_extract_file_changes` wraps stats access in a bare `except` to avoid surfacing Git errors as exceptions.

Added `SqliteFileFactStore` to `infrastructure/sqlite.py`:

- `file_facts` table with `UNIQUE(repository_id, commit_sha, file_path)`.
- `save_file_facts` iterates commits → file_changes, uses `INSERT OR IGNORE`.

Updated `interfaces/cli.py`:

- Prints `Files: N inserted, M reused` when both counts are not `None`.

Updated `composition.py`:

- Adds `file_fact_writer: FileFactWriter | None = None` override parameter.
- Creates `SqliteFileFactStore` pointing to the same `git-it.sqlite3`.
- Wires it as default `file_fact_writer` in `RepositoryIngestionService`.

### Follow-up

The next batch should add the commit read path (query service + SQLite reader) so the analysis pipeline can access ingested commits without reading the DB directly.
