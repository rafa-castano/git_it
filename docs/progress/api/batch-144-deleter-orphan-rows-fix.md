## Batch 144 — Fix repository-delete orphan rows: purge discussion_evidence and embedding_vectors

### Goal

Close two pre-existing gaps in `SqliteRepositoryDeleter`/`PostgresRepositoryDeleter`, found while
adding the spec-026 evidence tables to the purge list (batch 140): deleting a repository did NOT
remove its `discussion_evidence` rows (spec 022) or its `embedding_vectors` rows (spec 023),
leaving orphaned data behind that violates spec 008's "delete removes all data" contract.

### How it was found (evidence)

While wiring `release_evidence`/`advisory_evidence` into the deleter (batch 140), a grep of the
existing purge tuple showed it contained `github_context`, `file_facts`, `commit_analyses`,
`commit_facts`, `case_studies`, `repository_synopsis`, `repo_metadata`,
`default_branch_metadata`, `project_docs`, `ingestion_runs` — but NOT `discussion_evidence`
(added by spec 022, batch 107) or `embedding_vectors` (added by spec 023, batch 118). Both
stores write rows keyed by `repository_id`, so a delete left them orphaned. The existing
`test_delete_repo_removes_default_branch_row` proved the *pattern* was intended (every
repo-scoped table should be purged) — these two had simply been missed when their features
shipped.

### TDD

- **RED**: added `test_delete_repo_removes_discussion_evidence` and
  `test_delete_repo_removes_embeddings` to `tests/unit/test_api_delete.py`, mirroring the
  existing `test_delete_repo_removes_default_branch_row` pattern (save a row via the real store,
  `DELETE /api/repos/{id}`, assert the store now returns empty). Confirmed both FAILED for the
  right reason — the assertion showed the row surviving the delete (e.g. `Left contains one more
  item: EmbeddedChunk(...)`).
- **GREEN**: added `"discussion_evidence"` and `"embedding_vectors"` to the `existing_tables`-gated
  delete loop in both `SqliteRepositoryDeleter` (`infrastructure/sqlite/repository.py`) and
  `PostgresRepositoryDeleter` (`infrastructure/postgres/repository.py`), placed alongside the
  other repo-scoped evidence/metadata tables (before `ingestion_runs`). Both tests pass; the
  full `test_api_delete.py` suite is 10/10 green.

The tables remain gated by the `existing_tables` membership check, so a repository whose
discussion/embedding tables were never created (no `GITHUB_TOKEN`, no `OPENAI_API_KEY`) still
deletes cleanly — the same lazy-table-safety the deleter already had.

### Tests added

- `tests/unit/test_api_delete.py`: +2 regression tests (discussion evidence purge, embedding
  purge).

Full suite: unchanged pass count plus the 2 new tests, no regressions.

Gates: `ruff check .`, `mypy src/` clean.

### Gotchas

- These were genuine pre-existing bugs (specs 022/023 shipped their stores without updating the
  deleter), not something introduced by spec 026 — flagged to the user after batch 143 and fixed
  on explicit request. `release_evidence`/`advisory_evidence` (spec 026) were already correctly
  added to the deleter in batch 140, so this batch only backfills the two older misses.
- The delete loop's `# noqa: S608` (f-string table name into SQL) is safe here because the table
  names are a fixed, hardcoded tuple — never user input.

### Commits

- `fix: purge discussion_evidence and embedding_vectors rows on repository delete`
