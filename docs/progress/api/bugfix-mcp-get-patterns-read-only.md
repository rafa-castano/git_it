## Bug fix — MCP read-only tool `get_patterns` created the `commit_analyses` table on read

### Goal

Fix a read-only invariant violation in the MCP tool `get_patterns`: it routed
through `build_pattern_detection_service`, whose SQLite branch calls
`SqliteCommitAnalysisStore.initialize()`, running `CREATE TABLE IF NOT
EXISTS commit_analyses (...)` as a side effect of what should be a pure
read. This is the same class of bug fixed for `get_case_study` in `0fdcd83`
(spec 011 AC-5, and CODEX.md/AGENTS.md least-privilege rules for MCP read
tools).

### Root cause

`build_pattern_detection_service` in
`src/git_it/repository_ingestion/composition.py` is shared by two callers
with different privilege needs: `get_patterns` (a read-only MCP tool) and
`build_narrative_service` (part of the narrative-generation pipeline, which
legitimately provisions storage). Its SQLite branch always constructs a
`SqliteCommitAnalysisStore` and calls `.initialize()` on it before handing
the store to `PatternDetectionService` as the `analysis_reader`. Calling
`get_patterns` against a database that lacks `commit_analyses` therefore
created the table as a side effect, predating `bc03e0f` — it was not a
regression from that commit, just an existing defect that hadn't been
covered by a test yet.

### What `get_patterns` actually does

`get_patterns` does not read from a stored "patterns" table — patterns are
detected on the fly by `PatternDetectionService.detect()`, which reads raw
facts (`commit_facts`, `file_facts`) and per-commit `commit_analyses` rows
through several small reader ports (`commit_date_reader`,
`file_evidence_reader`, `reader` for file churn, `analysis_reader`,
`ownership_reader`) and computes hotspots/category counts/bugfix
recurrences/refactor waves in memory. None of the sibling readers
(`SqliteFileFactReader`, `SqliteCommitReader`) call `initialize()` — only
the analysis store did, via `build_pattern_detection_service`.

### Fix

Added `build_pattern_detection_service_reader()` in `composition.py`,
mirroring `build_pattern_detection_service()`'s backend selection (SQLite
vs PostgreSQL via `DATABASE_URL`) but never calling `.initialize()` /
`postgres_initialize()`. `get_patterns` in `registry.py` now uses this
reader and wraps `service.detect(...)` in a `sqlite3.OperationalError`
guard, returning the existing empty pattern report when the underlying
tables (e.g. `commit_analyses`) don't exist yet — instead of creating them.
`build_pattern_detection_service` (write-capable, `.initialize()`-calling)
is kept unchanged and still used by `build_narrative_service`, which is not
part of the read-only MCP surface.

### Tests

`tests/unit/test_mcp_readonly.py::test_patterns_tool_does_not_create_missing_table`
— was RED (asserted `commit_analyses` not created; failed because
`build_pattern_detection_service`'s `initialize()` call created it), now
GREEN.

Updated `tests/unit/test_tools_registry.py::test_registry_delegates_reads_to_backend_aware_builders`
to monkeypatch `build_pattern_detection_service_reader` instead of
`build_pattern_detection_service`.

### Sibling read tools checked

- `list_repositories`, `search_commits`, `get_contributors`, `get_case_study`
  all route through non-initializing readers already (checked in `0fdcd83`
  and re-confirmed here); no further defect found among the five read-only
  MCP tools.

### Commit

`fix: stop get_patterns from creating tables on read`
