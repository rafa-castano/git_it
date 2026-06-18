# Batch 63 — PostgreSQL backend as alternative to SQLite

## Goal

Add PostgreSQL as an optional persistence backend selectable via `DATABASE_URL`, keeping the SQLite path 100% unchanged.

## What was built

### `migrations/001_initial.sql`

Single SQL file with all table definitions in PostgreSQL syntax:

- `BIGSERIAL PRIMARY KEY` instead of `INTEGER PRIMARY KEY AUTOINCREMENT`
- `NOW()` instead of `datetime('now')` for default timestamps
- `ON CONFLICT ... DO NOTHING` instead of `INSERT OR IGNORE`
- All tables wrapped in `CREATE TABLE IF NOT EXISTS`
- Includes `github_context` table added in batch 58

### `src/git_it/repository_ingestion/infrastructure/postgres.py`

PostgreSQL adapters mirroring the SQLite equivalents:

| Adapter | SQLite equivalent | Port implemented |
|---------|-------------------|-----------------|
| `PostgresIngestionRunStore` | `SqliteIngestionRunStore` | `IngestionRunWriter` / `IngestionRunReader` |
| `PostgresCommitStore` | `SqliteCommitFactStore` | `CommitFactWriter` |
| `PostgresFileFactStore` | `SqliteFileFactStore` | `FileFactWriter` |
| `PostgresCommitReader` | `SqliteCommitReader` | `CommitSummaryReader`, `CommitDateReader` |
| `PostgresCommitAnalysisStore` | `SqliteCommitAnalysisStore` | `CommitAnalysisWriter`, `CommitAnalysisReader`, `TemporalAnalysisReader` |
| `PostgresFileFactReader` | `SqliteFileFactReader` | `FileFactReader`, `OwnershipReader`, `FileEvidenceReader` |
| `PostgresCaseStudyStore` | `SqliteCaseStudyStore` | `CaseStudyStore`, `RepoContextReader` |
| `PostgresRepositoryListReader` | `SqliteRepositoryListReader` | `RepositoryListReader` |
| `PostgresCommitCountReader` | `SqliteCommitCountReader` | `CommitCountReader` |
| `PostgresCommitWithAnalysisReader` | `SqliteCommitWithAnalysisReader` | `CommitWithAnalysisReader` |
| `PostgresContributorReader` | `SqliteContributorReader` | `ContributorReader` |
| `PostgresGithubContextCache` | `SqliteGithubContextCache` | GitHub context cache |

Uses `psycopg` (v3) with `%s` placeholders. Connection-per-operation pattern (no pooling), matching SQLite adapters.

Module-level `initialize(conninfo)` function runs `migrations/001_initial.sql`.

### SQL translation notes

- `json_extract(data, '$.category')` (SQLite) → `data::json->>'category'` (PostgreSQL JSON path operator)
- `substr(committed_at, 1, 10)` works in both dialects
- `datetime('now')` default in SQLite → `TO_CHAR(NOW() AT TIME ZONE 'UTC', ...)` in column default; but `created_at` is TEXT in both, so `list_analyses_since` ordering by string works the same way

### `src/git_it/repository_ingestion/composition.py`

Added `_get_db_backend()` helper that reads `DATABASE_URL` and returns `('postgres', conninfo)` or `('sqlite', '')`.

Updated `build_repository_ingestion_service`, `build_commit_analysis_service`, `build_pattern_detection_service`, and `build_narrative_service` to branch on backend type. SQLite path is unchanged.

### `docker-compose.yml`

`db` service (postgres:16-alpine) and `api` service with `DATABASE_URL` wired. Migration SQL mounted into `docker-entrypoint-initdb.d/`.

### `.env.example`

Documents `DATABASE_URL`, `GIT_IT_API_KEY`, `ANTHROPIC_API_KEY`, and `GITHUB_TOKEN`.

### `tests/unit/test_postgres_adapters.py`

8 tests covering insert + read roundtrips for the key stores. All skip automatically when `DATABASE_URL` is not a PostgreSQL URL:

```python
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL.startswith("postgresql"),
    reason="DATABASE_URL not set to PostgreSQL — skipping Postgres adapter tests"
)
```

### `.github/workflows/ci.yml`

Added `services.postgres` (postgres:16-alpine with health check) and `DATABASE_URL` env var on the pytest step so Postgres tests run in CI.

## Key decisions

- **Connection-per-operation**: matches SQLite pattern; no pooling complexity for now.
- **Additive only**: SQLite remains the default; no existing test is touched.
- **`psycopg[binary]` was already in `pyproject.toml`**: no dependency change needed.
- **Text timestamps**: `committed_at` and `created_at` are stored as TEXT in both backends (ISO-8601 strings), so ordering and range queries work identically.
