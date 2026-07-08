## Batch 159 — Incremental commit extraction (spec 030)

### Goal

Stop re-diffing the whole history on every ingest. `GitPythonCommitExtractor.extract_commits()`
walked the full history and called `commit.stats.files` for **every** commit — GitPython runs that
as a `git diff` subprocess per commit — and then `INSERT OR IGNORE` (keyed by
`(repository_id, sha)`) threw the result away for every commit already stored. "Refresh all"
(spec 028) runs that primitive per repository sequentially, so each refresh cost
`Σ(all commits per repo)` redundant `git diff` spawns even when nothing changed upstream. Spec 030
makes extraction incremental: the service reads the already-stored SHAs and passes them to the
extractor as a **skip-set**; the extractor skips both the `ExtractedCommit` build and the per-commit
`git diff` for skipped SHAs. New commits are extracted and appended exactly as before — a pure
performance optimization with byte-identical stored facts.

### What was added

**Port + extractor**
- `StoredCommitShaReader` port (`application/ports.py`): `read_stored_shas(repository_id) -> set[str]`,
  a lightweight `SELECT sha FROM commit_facts WHERE repository_id = ?`. Added to `__all__`.
- `CommitExtractor.extract_commits` signature changed to
  `extract_commits(skip_shas: frozenset[str] = frozenset())`. The default preserves the old no-arg
  call site and full-extraction behavior (AC-05).
- `GitPythonCommitExtractor.extract_commits` (`infrastructure/commits.py`): for any commit whose
  `hexsha` is in the skip-set it `continue`s before touching `commit.stats` — skipping the expensive
  `git diff` (AC-02) and emitting no `ExtractedCommit` for it (AC-03). `commit.hexsha` is cheap
  metadata, read during the normal history walk (no walk-level Git optimization, per Non-goals §4).

**Adapters**
- `SqliteStoredCommitShaReader` (`infrastructure/sqlite/commits.py`) and
  `PostgresStoredCommitShaReader` (`infrastructure/postgres/commits.py`), both a parameterized
  `SELECT sha` returning a `set[str]` (empty set for an unknown repo). Exported from both package
  `__init__.py` files.

**Service wiring**
- `RepositoryIngestionService` gains an optional `stored_commit_sha_reader` constructor param. In
  `ingest()`, right before extraction: if the reader is wired, read the skip-set for the repository
  and pass `extract_commits(frozenset(skip_shas))`; if unwired, pass an empty skip-set (full
  extraction). AC-11 fallback: if the reader **raises**, degrade to an empty skip-set (full
  extraction) — never crash ingest.
- AC-07: when the reader is wired, `commits_reused` is reported as the **skip-set size** (the writer
  now only ever sees new commits); `commits_inserted` still reflects actually-inserted new commits.
  Without a reader, `commits_reused` falls back to the writer's per-row tally (existing behavior).

**Composition**
- `build_repository_ingestion_service` builds the backend-appropriate reader
  (`Sqlite`/`PostgresStoredCommitShaReader` via the existing `_get_db_backend()` seam, mirroring the
  commit-fact writer) and injects it. So **Refresh all** and re-ingest get incremental extraction for
  free. An explicit `stored_commit_sha_reader` argument still overrides the default.

### Tests added

- New: `test_stored_commit_sha_reader.py` — SQLite roundtrip (stored SHAs as a set, empty set for
  unknown repo, per-repository scoping).
- Extended `test_git_commit_extractor.py` — spy-commit tests asserting `commit.stats` is accessed
  **only** for new commits and never for skip-set members (AC-02), zero stats accesses when all
  commits are skipped (AC-08), and empty-skip-set == no-arg full extraction (AC-05).
- Extended `test_repository_ingestion_service.py` — reader read + skip-set passed when wired (AC-01),
  empty skip-set when unwired (AC-05), skip-set size reported as reused (AC-07), degrade-to-full on a
  raising reader (AC-11), and an AC-04 equivalence test proving an incremental ingest (seed a partial
  history, then ingest the full history with the reader wired) stores commit_facts/file_facts rows
  identical to a full ingest of the same history. Existing `FakeCommitExtractor` doubles updated to
  accept the optional `skip_shas`.
- Extended `test_repository_ingestion_composition.py` — default wiring test asserts a
  `SqliteStoredCommitShaReader` is injected. `NullCommitExtractor` double updated.
- Extended `test_postgres_adapters.py` — `PostgresStoredCommitShaReader` roundtrip + empty-set,
  `DATABASE_URL`-gated (skips cleanly without a Postgres URL).
- `tests/integration/conftest.py` — the `extract_commits` monkeypatch lambda now accepts the optional
  `skip_shas`.
- Full unit suite green: **1210 passed, 38 skipped** (Postgres tests skipped without `DATABASE_URL`).

### Gotchas

- **The extractor's broad `try/except` hides raises.** `_extract_file_changes` swallows any exception
  from `commit.stats`, so a spy that *raises* on stats access could not prove the skip logic (a wrong
  skip would be silently caught). The tests therefore **count** stats accesses per SHA and assert the
  count is zero for skipped commits — a stronger, non-swallowable guarantee.
- **`commits_reused` semantics change only when a reader is wired.** With the skip-set in play the
  writer sees only new commits, so its own `reused` tally would read 0 and be misleading; the
  service substitutes the skip-set size. The no-reader path is untouched, so existing tests that
  assert the writer's reused count still hold.
- **Orphans are tolerated, not pruned** (Non-goal §4). A stored SHA absent from the current history
  after an upstream rebase/force-push is simply never encountered during the walk — no effect, no
  error, and it stays in the DB until a re-analyze/delete.

### Commits

- `feat: incremental commit extraction — skip already-stored commits (spec 030)`
