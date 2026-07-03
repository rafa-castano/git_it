## Batch 104 — Split PostgreSQL infrastructure into a cohesive package

### Goal

`src/git_it/repository_ingestion/infrastructure/postgres.py` had grown to 1055 lines and
16 classes covering unrelated concerns (ingestion runs, commit/file facts, analyses, case
studies, contributors, GitHub context cache, repo metadata, repository listing and
deletion) — the same shape of problem batch 103 fixed for the SQLite adapters. Pure
internal tech-debt cleanup: split the single module into a cohesive package with zero
behavior change, mirroring batch 103 exactly.

### What was added

Converted `infrastructure/postgres.py` into a package `infrastructure/postgres/` with:

- `_common.py` — shared private helpers: `_optional_str`, `_bool_to_int`, `_int_to_bool`,
  `_record_from_row`, `_extract_github_username`, plus the public `initialize(conninfo)`
  entry point (runs `migrations/001_initial.sql`). Kept dependency-free (leaf module) so
  every other sub-module can import from it without circular imports.
- `ingestion.py` — `PostgresIngestionRunStore`
- `commits.py` — `PostgresCommitStore`, `PostgresCommitReader`, `PostgresCommitCountReader`,
  `PostgresCommitWithAnalysisReader`
- `files.py` — `PostgresFileFactStore`, `PostgresFileFactReader`
- `analysis.py` — `PostgresCommitAnalysisStore`, `PostgresCaseStudyStore`,
  `PostgresSynopsisStore` (`_REPO_CONTEXT_MAX_CHARS` stays local here — only
  `PostgresCaseStudyStore` uses it, matching how batch 103 kept it local to sqlite's
  `analysis.py`)
- `contributors.py` — `PostgresContributorReader` (`_BOT_PATTERN` stays local here — only
  this class uses it, matching sqlite's `contributors.py`)
- `github.py` — `PostgresGithubContextCache`, `PostgresRepoMetadataStore`,
  `PostgresDefaultBranchStore` (package-relative; distinct from `infrastructure/github.py`,
  the GitHub API fetcher)
- `repository.py` — `PostgresRepositoryListReader`, `PostgresRepositoryDeleter`
- `__init__.py` — re-exports all 16 classes plus the public `initialize` function via an
  explicit `__all__`, following the same facade pattern batch 103 used for
  `infrastructure/sqlite/__init__.py`. The two existing import sites
  (`repository_ingestion/composition.py` and `tests/unit/test_postgres_adapters.py`) keep
  resolving unchanged — neither was touched.

Class bodies were moved verbatim; only import statements were adjusted per sub-module to
pull in just what each file needs (e.g. `commits.py` needs `CommitRecord` from
`commit_query_service`, `github.py` needs `GithubContext`/`RepoMetadata`/
`LanguageBreakdown`).

### Tests added

None — pure refactor; the existing 811-test suite is the gate. Baseline (`ef60665`, after
batch 103) and post-split runs both report `811 passed, 18 skipped`.

### Gotchas

- **`initialize()` migrations path depth**: the original `postgres.py` computed the
  migrations file path as `Path(__file__).parents[5] / "migrations" / "001_initial.sql"`.
  Moving that function into `postgres/_common.py` nests it one directory level deeper, so
  the index had to become `parents[6]` to resolve to the *exact same* absolute directory as
  before (verified by comparing `old_file.parents[5] == new_file.parents[6]` before
  committing) — this is a pure path-depth adjustment for zero behavior change, not a
  logic change. `initialize()` is exercised by `tests/unit/test_postgres_adapters.py` only
  when `DATABASE_URL` points at a real PostgreSQL instance (skipped otherwise, part of the
  18 expected skips locally).
- **`postgres/github.py` vs `infrastructure/github.py`**: same non-issue batch 103 already
  established for `sqlite/github.py` — these are distinct modules at different package
  depths (`infrastructure.postgres.github` vs. `infrastructure.github`), so no import site
  needs to disambiguate between them.
- **No circular imports needed resolving**: no two classes were mutually dependent across
  sub-modules, so the same one-domain-per-file split batch 103 used worked here too.
  `_common.py` has zero imports from sibling sub-modules, keeping it a leaf.
- **`__init__.py` re-export pattern**: explicit `from .module import Name` plus
  `__all__ = [...]`, matching `sqlite/__init__.py`'s convention, so ruff's `F401` (unused
  import) rule doesn't fire on the facade module. `initialize` is re-exported alongside the
  16 classes since it's the only non-class public name the two external import sites rely
  on.

### Commits

- `refactor: split postgres infrastructure into a cohesive package`
