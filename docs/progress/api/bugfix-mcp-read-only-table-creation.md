## Bug fix — MCP read-only tool created the `case_studies` table on read

### Goal

Fix a security regression introduced by `bc03e0f` ("route read tools through
backend-aware persistence"): the read-only MCP tool `get_case_study` started
mutating the database — creating the `case_studies` table when it was
missing — which violates the read-only invariant required by spec 011 AC-5
(and CODEX.md/AGENTS.md least-privilege rules for MCP read tools).

### Root cause

`bc03e0f` changed `get_case_study` in `src/git_it/tools/registry.py` from a
hardcoded `SqliteCaseStudyStore(db_path)` to
`build_case_study_store(project_root=project_root)`. That factory
(`src/git_it/repository_ingestion/composition.py`) calls `store.initialize()`
on construction, which runs `CREATE TABLE IF NOT EXISTS case_studies (...)`.
The pre-regression code never called `initialize()` for reads — it queried
directly and caught `sqlite3.OperationalError` to handle a missing table
gracefully. Routing the read path through the write-capable factory silently
reintroduced a `CREATE TABLE` side effect on every case-study read.

### Fix

Added a new, read-only factory `build_case_study_reader()` in
`composition.py` that mirrors `build_case_study_store()`'s backend selection
(SQLite vs PostgreSQL via `DATABASE_URL`) but never calls `initialize()`.
`get_case_study` in `registry.py` now uses this reader and restores the
`sqlite3.OperationalError` guard around the read calls, returning the empty
case-study response when the table doesn't exist yet — instead of creating
it. Backend-awareness (the actual intent of `bc03e0f`) is preserved; only the
table-creation side effect is removed from the read path.

### Sibling read tools checked

- `search_commits`, `get_contributors`, `list_repositories` route through
  `build_commit_with_analysis_reader`, `build_contributor_reader`, and
  `build_repository_list_reader` respectively — none of these factories call
  `.initialize()`, so they do not share this defect.
- `get_patterns` routes through `build_pattern_detection_service`, which does
  call `.initialize()` on its analysis store. This predates `bc03e0f` (the
  same factory call existed before the commit) and is not part of this
  regression, so it was left untouched — out of scope for a surgical fix of
  the `bc03e0f` regression, and no test currently proves it as a defect.

### Tests

`tests/unit/test_mcp_readonly.py::test_case_study_tool_does_not_create_missing_table`
— was RED (asserted `case_studies` not created; failed against the regression),
now GREEN.

Updated `tests/unit/test_tools_registry.py::test_registry_delegates_reads_to_backend_aware_builders`
to monkeypatch the corrected `build_case_study_reader` name (it previously
patched `build_case_study_store`, which encoded the buggy delegation as an
implementation detail).

### Commit

`fix: stop get_case_study from creating tables on read`
