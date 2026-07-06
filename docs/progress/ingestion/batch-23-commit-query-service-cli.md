## Batch 23 — Commit query service and `git-it commits` CLI command

### Goal

Add the commit read path so the rest of the pipeline (analysis, pattern detection, narrative) can query ingested commits through a stable application service rather than touching SQLite directly.

### Source of truth

- `docs/specs/001-repository-ingestion.md` query service DTO requirements
- `docs/specs/002-commit-analysis.md` — commit analysis requires reading commits back
- Layered architecture: `CommitRecord` DTO lives in application, `SqliteCommitReader` in infrastructure

### Examples

CLI commit listing:

```text
$ git-it commits https://github.com/owner/repo
abc1234  2026-01-15  Add user authentication  (Alice)
def5678  2026-01-14  Fix login bug  (Bob)
```

Empty repository:

```text
No commits stored for this repository. Run 'git-it ingest <url>' first.
```

With limit:

```text
$ git-it commits --limit 5 https://github.com/owner/repo
```

### Tests

New `tests/unit/test_sqlite_commit_reader.py`:

- `test_sqlite_commit_reader_returns_empty_list_when_no_commits_stored`
- `test_sqlite_commit_reader_returns_commits_for_repository`
- `test_sqlite_commit_reader_returns_commits_in_reverse_chronological_order`
- `test_sqlite_commit_reader_limits_result_when_limit_is_specified`
- `test_sqlite_commit_reader_isolates_commits_by_repository`

New `tests/unit/test_repository_commit_query_service.py`:

- `test_list_commits_delegates_to_reader`
- `test_list_commits_passes_limit_to_reader`
- `test_list_commits_returns_empty_list_when_reader_has_none`

New `tests/unit/test_commits_cli.py`:

- `test_commits_cli_prints_recent_commits` — sha[:7], message, author in output.
- `test_commits_cli_shows_message_when_no_commits_stored` — "No commits" line.
- `test_commits_cli_passes_limit_to_query_service` — `--limit 5` propagated to service.

### Production behavior

New `application/commit_query_service.py`:

- `CommitRecord` frozen dataclass (repository_id, sha, committed_at, message, author_name, committer_name, parent_shas).
- `CommitReader` protocol with `list_commits_for_repository(repository_id, *, limit=None)`.
- `RepositoryCommitQueryService` with `list_commits(repository_id, *, limit=None)`.

Added `SqliteCommitReader` to `infrastructure/sqlite.py`:

- SELECTs from `commit_facts` by `repository_id` ordered by `committed_at DESC`.
- Supports optional `LIMIT`.
- Deserializes `parent_shas` from JSON array.

Updated `composition.py`:

- Added `build_repository_commit_query_service(*, project_root)` factory.

Updated `interfaces/cli.py`:

- Added `commits` subparser with `--limit` (default 20).
- Added `CommitQueryFactory` protocol and `_default_commit_query_factory`.
- Added `_run_commits` and `_print_commits` helpers.
- `main` gains `commit_query_factory` injectable parameter for testability.

### Follow-up

The next batch implements `git-it analyze <url>` using a provider-agnostic LLM client backed by LiteLLM.
