## Batch 21 — Commit fact SQLite persistence and idempotent inserted/reused counts

### Goal

Persist extracted commits into SQLite using idempotent `INSERT OR IGNORE` so that re-ingestion reports inserted vs reused counts instead of just extracted counts.

### Source of truth

- `docs/specs/001-repository-ingestion.md` commit fact persistence and idempotency requirements
- Batch 20 `CommitExtractor` protocol and `GitPythonCommitExtractor`
- `CommitFact` unique by `(repository_id, sha)` — re-ingestion must produce distinct inserted/reused tallies

### Examples

First ingestion of a repository with 3 commits:

```text
Ingestion status: CLONING_OR_FETCHING
Repository: owner/repo
Canonical URL: https://github.com/owner/repo
Commits: 3 inserted, 0 reused
Run ID: run-abc123
```

Re-ingestion of the same repository (all commits already present):

```text
Commits: 0 inserted, 3 reused
```

Mixed re-ingestion (1 new commit since last run):

```text
Commits: 1 inserted, 3 reused
```

Same SHA in two different repositories is treated as two distinct facts:

```text
repo-1 / sha-aaa -> inserted=1
repo-2 / sha-aaa -> inserted=1  # independent
```

### Tests

New test file `tests/unit/test_commit_fact_store.py`:

- `test_sqlite_commit_fact_store_inserts_new_commits` — 3 new commits → inserted=3, reused=0.
- `test_sqlite_commit_fact_store_marks_existing_commits_as_reused_on_reingest` — same 3 commits re-saved → inserted=0, reused=3.
- `test_sqlite_commit_fact_store_tracks_mixed_insertions_and_reuses` — 2 existing + 1 new → inserted=1, reused=2.
- `test_sqlite_commit_fact_store_treats_same_sha_as_independent_across_repositories` — same SHA in two repos both count as inserted.

Updated `tests/unit/test_repository_ingestion_service.py`:

- Renamed `test_ingestion_service_extracts_commits_after_successful_clone_or_fetch` to `test_ingestion_service_calls_extractor_after_successful_clone_or_fetch` — now only asserts the extractor is called once.
- Added `test_ingestion_service_persists_commits_and_reports_inserted_reused` — fake extractor + fake writer → `commits_inserted=2`, `commits_reused=1` on the result.
- Added `test_ingestion_service_does_not_report_counts_without_fact_writer` — extractor present but no writer → both counts are `None`.
- Updated `test_ingestion_service_skips_extraction_when_no_extractor_is_wired` — checks `commits_inserted is None` and `commits_reused is None`.

Updated `tests/unit/test_repository_ingestion_cli.py`:

- `test_ingest_cli_prints_commit_count_in_success_output_when_present` — now uses `commits_inserted=3, commits_reused=2` and asserts `Commits: 3 inserted, 2 reused`.
- `test_ingest_cli_omits_commit_count_when_absent` — uses `commits_inserted=None, commits_reused=None` and asserts no `Commits:` line.

Updated `tests/unit/test_repository_ingestion_composition.py`:

- `test_build_repository_ingestion_service_wires_gitpython_extractor_by_default` — now asserts `commits_inserted == 2` and `commits_reused == 0` instead of the removed `commits_extracted`.

### Production behavior

Added to `application/ports.py`:

- `CommitPersistenceResult` frozen dataclass with `inserted: int` and `reused: int`.
- `CommitFactWriter` protocol with `save_commit_facts(commits, *, repository_id) -> CommitPersistenceResult`.

Updated `IngestionResult` in `application/service.py`:

- Replaced `commits_extracted: int | None` with `commits_inserted: int | None` and `commits_reused: int | None`.

Updated `RepositoryIngestionService`:

- Accepts `commit_fact_writer: CommitFactWriter | None = None`.
- After extraction, calls `save_commit_facts` if writer is wired and populates both count fields.
- When no writer is wired, both counts remain `None`.

Added `SqliteCommitFactStore` to `infrastructure/sqlite.py`:

- `commit_facts` table with `UNIQUE(repository_id, sha)` constraint.
- `save_commit_facts` uses `INSERT OR IGNORE`; `rowcount == 1` → inserted, `rowcount == 0` → reused.
- `parent_shas` serialized as a JSON array.
- `initialize()` creates parent directories and the table idempotently.

Updated `_print_ingestion_result` in `interfaces/cli.py`:

- Prints `Commits: N inserted, M reused` when both `commits_inserted` and `commits_reused` are not `None`.

Updated `composition.py`:

- Added `commit_fact_writer: CommitFactWriter | None = None` override parameter.
- Creates `SqliteCommitFactStore` pointing to the same `git-it.sqlite3` database as the run store.
- Passes it as `commit_fact_writer` to `RepositoryIngestionService` by default.

### Follow-up

The next batch should add file-level change persistence and fix the final ingestion status from CLONING_OR_FETCHING to COMPLETED.
