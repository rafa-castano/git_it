## Batch 103 — Split SQLite infrastructure into a cohesive package

### Goal

`src/git_it/repository_ingestion/infrastructure/sqlite.py` had grown to 1239 lines and
16 classes covering unrelated concerns (ingestion runs, commit/file facts, analyses,
case studies, contributors, GitHub context cache, repo metadata, repository listing and
deletion). Pure internal tech-debt cleanup: split the single module into a cohesive
package with zero behavior change, so future changes to one concern (e.g. contributor
stats) don't require reading through unrelated code (e.g. GitHub context caching) in the
same file.

### What was added

Converted `infrastructure/sqlite.py` into a package `infrastructure/sqlite/` with:

- `_common.py` — shared private helpers: `_record_from_row`, `_optional_str`,
  `_bool_to_sqlite`, `_sqlite_to_bool`, `_extract_github_username`. Kept dependency-free
  (leaf module) so every other sub-module can import from it without circular imports.
- `ingestion.py` — `SqliteIngestionRunStore`
- `commits.py` — `SqliteCommitFactStore`, `SqliteCommitReader`, `SqliteCommitCountReader`,
  `SqliteCommitWithAnalysisReader`
- `files.py` — `SqliteFileFactStore`, `SqliteFileFactReader`
- `analysis.py` — `SqliteCommitAnalysisStore`, `SqliteCaseStudyStore`, `SqliteSynopsisStore`
  (`_REPO_CONTEXT_MAX_CHARS` stays local here — only `SqliteCaseStudyStore` uses it)
- `contributors.py` — `SqliteContributorReader` (`_BOT_PATTERN` stays local here — only
  this class uses it)
- `github.py` — `SqliteGithubContextCache`, `SqliteRepoMetadataStore`,
  `SqliteDefaultBranchStore`
- `repository.py` — `SqliteRepositoryListReader`, `SqliteRepositoryDeleter`
- `__init__.py` — re-exports all 16 classes via an explicit `__all__`, following the same
  facade pattern already used by `git_it/chat/__init__.py` and `git_it/tools/__init__.py`.
  Every existing `from git_it.repository_ingestion.infrastructure.sqlite import
  <Class>` import site (~22 test files plus `composition.py`) keeps resolving unchanged —
  none of those import sites were touched.

Class bodies were moved verbatim; only import statements were adjusted per sub-module to
pull in just what each file needs (e.g. `commits.py` needs `CommitRecord` from
`commit_query_service`, `github.py` needs `GithubContext`/`RepoMetadata`/
`LanguageBreakdown`).

### Tests added

None — pure refactor; the existing 811-test suite is the gate. Baseline (`88d50a1`) and
post-split runs both report `811 passed, 18 skipped`.

### Gotchas

- **Name collision risk**: the new `infrastructure/sqlite/github.py` sub-module lives
  right next to the pre-existing `infrastructure/github.py` (GitHub API fetcher). They are
  distinct modules at different package depths — `infrastructure.sqlite.github` vs.
  `infrastructure.github` — so no import ever needs to disambiguate between them from
  outside the `sqlite` package, and internal imports inside `sqlite/github.py` use
  fully-qualified `git_it.repository_ingestion.domain.*` paths rather than a relative
  import that could look ambiguous.
- **No circular imports needed resolving**: no two classes were mutually dependent across
  sub-modules, so a straightforward one-domain-per-file split worked without merging any
  classes together. `_common.py` has zero imports from sibling sub-modules, guaranteeing
  it stays a leaf.
- **`__init__.py` re-export pattern**: used explicit `from .module import Name` plus
  `__all__ = [...]` (matching the existing convention in `chat/__init__.py` and
  `tools/__init__.py`) rather than `import ... as ...` re-export syntax, so `ruff`'s `F401`
  (unused import) rule doesn't fire on the facade module.
- `_extract_github_username` is only actually consumed by `SqliteContributorReader`
  (`contributors.py`), but was kept in `_common.py` per the planned grouping for
  consistency with the other shared row/bool helpers — it was not importable from outside
  the old module by any external caller, so this placement is purely organizational and
  has no behavior impact.

### Commits

- `refactor: split sqlite infrastructure into a cohesive package`
