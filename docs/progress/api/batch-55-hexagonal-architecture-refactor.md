## Batch 55 — Hexagonal architecture refactor of API routes

### Goal

Remove all raw `sqlite3.connect()` calls from route handlers. Every DB access must go through a port (Protocol) + adapter pattern, consistent with ADR-006 and the rest of the codebase.

### What was added

**New ports in `ports.py`:**
- `RepositoryRecord` dataclass + `RepositoryListReader` protocol
- `CommitCountReader` protocol (`count_commits`, `count_analyses`)
- `CommitWithAnalysisRecord` dataclass + `CommitWithAnalysisReader` protocol
- `ContributorRecord` dataclass + `ContributorReader` protocol

**New adapters in `sqlite.py`:**
- `SqliteRepositoryListReader` — multi-table JOIN for the repos list endpoint
- `SqliteCommitCountReader` — two COUNT queries for the estimate endpoint
- `SqliteCommitWithAnalysisReader` — parameterized JOIN + ORDER BY + LIMIT for the commits endpoint
- `SqliteContributorReader` — three-query contributor stats with `_BOT_PATTERN` and `_extract_github_username` helpers

**Route refactors in `repos.py`:**
- `list_repos` → `SqliteRepositoryListReader`
- `get_case_study` → existing `SqliteCaseStudyStore` (already had a `get_case_study` method; route was bypassing it)
- `estimate_analyze` → `SqliteCommitCountReader`
- `get_commits` → `SqliteCommitWithAnalysisReader`
- `get_contributors` → `SqliteContributorReader`

**Additional cleanup:**
- `sqlite3` import removed from `repos.py` entirely
- Duplicate inline `ALTER TABLE` DDL migration removed from `get_contributors` (it lives only in `SqliteCommitFactStore.initialize()`)
- `_extract_github_username` moved from nested inner function to module level in `repos.py`
- `_BOT_PATTERN` regex moved to `sqlite.py` where it's used

### Tests

All 520 existing tests passed without modification after the refactor — confirming the refactor changed only internal structure, not observable behavior.

### Gotchas

- `get_case_study` was the only route where the adapter existed but wasn't wired — a silent divergence from the architecture
- Removing the duplicate `ALTER TABLE` migration from the route is safe because `SqliteCommitFactStore.initialize()` always runs before any route is called (it runs during the ingest flow which creates the DB)

### Commits

- `refactor: hexagonal architecture — remove raw SQL from API route handlers`
