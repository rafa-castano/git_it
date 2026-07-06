# Batch 132 — Project-doc capture wired into RepositoryIngestionService (spec 025, slice 3)

## Goal

Wire the README/CHANGELOG capture built in batches 130-131
(`ProjectDocContent`, `GitPythonProjectDocReader`,
`SqliteProjectDocStore`/`PostgresProjectDocStore`) into the actual ingestion
flow, so a real ingestion run persists a repository's project-doc excerpt —
purely additive, optional-port wiring, mirroring spec 020's default-branch
capture exactly.

## What was added

### Application (`application/service.py`)

- `RepositoryIngestionService` gained two optional constructor ports
  (`project_doc_reader: ProjectDocReader | None`, `project_doc_writer:
  ProjectDocWriter | None`), same shape and same guard as the existing
  `default_branch_reader`/`default_branch_writer` pair.
- Inside `ingest()`, right after the default-branch capture block (which sits
  right after a successful `clone_or_fetch`), a new block calls
  `project_doc_reader.get_project_docs(repository_id)` and, only if it
  returns a non-`None` `ProjectDocContent` and a writer is wired, calls
  `project_doc_writer.save_project_docs(content)`. Never called on a
  `GitGatewayError` — same early-return guard already protects both blocks.

### Composition (`composition.py`)

- `build_project_doc_store(*, project_root) -> SqliteProjectDocStore |
  PostgresProjectDocStore` — backend-aware factory, identical shape to
  `build_default_branch_store` (calls `.initialize()` for SQLite only).
- `build_repository_ingestion_service(...)` gained matching optional keyword
  args (`project_doc_reader`, `project_doc_writer`) with the same
  override-or-default resolution pattern already used for the default-branch
  ports: default reader is `GitPythonProjectDocReader(cache_path=cache_path)`,
  default writer is `build_project_doc_store(project_root=project_root)`.

## Tests added

4 new tests in `tests/unit/test_repository_ingestion_service.py`, mirroring
the existing default-branch wiring section structure exactly:

- `test_ingestion_service_persists_project_docs_after_successful_clone` —
  reader called with the repository id, resolved `ProjectDocContent` passed
  whole to the writer.
- `test_ingestion_service_does_not_persist_project_docs_when_reader_returns_none`
  — writer never called when the reader resolves nothing.
- `test_ingestion_service_skips_project_doc_reader_without_wiring` —
  ingestion still completes normally when neither port is wired (existing
  default, unchanged).
- `test_ingestion_service_does_not_read_project_docs_on_gateway_failure` —
  reader/writer never touched when `clone_or_fetch` raises `GitGatewayError`.

Full suite: 980 passed, 27 skipped (all pre-existing default-branch wiring
tests in the same file still pass unchanged, confirming no regression to the
adjacent spec 020 feature).

Quality gates: `ruff check .` (all checks passed), `ruff format --check .`
(193 files already formatted), `mypy src/` (no issues, 80 source files),
`pytest -q` (980 passed, 27 skipped).

## Gotchas

- **Argument shape differs from the default-branch pair, by design.**
  `default_branch_writer.save_default_branch(repository_id, branch)` takes
  two separate primitives; `project_doc_writer.save_project_docs(content)`
  takes the whole `ProjectDocContent` object, which already carries
  `repository_id` inside it (batch 130). The reader call still needs
  `repository_id` passed in explicitly
  (`get_project_docs(self._repository_id or "")`), even though
  `GitPythonProjectDocReader` only uses it to stamp the returned
  dataclass's `repository_id` field — it doesn't need it to locate the bare
  clone (that's bound at construction via `cache_path`).
- **Ruff import-sort caught a real ordering issue** in the composition.py
  edit (new `PostgresProjectDocStore`/`SqliteProjectDocStore` imports plus the
  new `infrastructure.project_docs` import needed re-sorting) — fixed via
  `ruff check . --fix`, no behavior change.
- **No new NarrativeService or prompt work in this batch** — deferred to
  batch 133 per spec 025's TDD-ordering ("Domain → reader → stores → service
  wiring → NarrativeService prompt integration").

## Commits

- (recorded in the batch commit for this file)
