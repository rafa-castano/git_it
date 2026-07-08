# Spec 030: Incremental Commit Extraction (Skip Already-Stored Commits)

**Status:** Implemented
**Spec number:** 030
**Author:** Rafael Castaño
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: Architecture Agent, Quality Agent
Created: 2026-07-08
Updated: 2026-07-08

## 1. Summary

Every ingest re-extracts the **entire** commit history from the local bare clone
and, for **each** commit, computes `commit.stats.files` — which GitPython
implements as a `git diff` subprocess against the commit's parent
(`src/git_it/repository_ingestion/infrastructure/commits.py:46-77`). The commit
writer then persists with `INSERT OR IGNORE` keyed by `(repository_id, sha)`
(`infrastructure/sqlite/commits.py:61`), so every already-stored commit's
expensive diff is computed and then **thrown away** (`reused++`).

"Refresh all" (spec 028) calls this same `ingest` primitive sequentially for every
tracked repository (`application/refresh_all_service.py:124`). The result is
`Σ(all commits per repo)` `git diff` subprocess calls on **every** refresh — even
when zero commits are new — which is why "Refresh all" is slow locally.

This spec makes extraction **incremental**: the ingest service reads the set of
commit SHAs already stored for the repository and passes it to the extractor as a
**skip-set**; the extractor skips both the `ExtractedCommit` build and the
per-commit `git diff` for any SHA already stored. New commits are extracted and
appended exactly as today. Nothing is deleted; already-analyzed commits are never
touched. This is a **pure performance optimization** — the stored facts after an
incremental ingest are identical to the stored facts after a full ingest, for the
same underlying history.

## 2. Problem

`GitPythonCommitExtractor.extract_commits()` recomputes the full history's diffs on
every ingest, discarding the work for the (usually vast majority of) commits that
are already stored. On a repository with thousands of commits, one refresh costs
thousands of `git diff` subprocess spawns; "Refresh all" multiplies that by the
repository count, sequentially. The dominant cost is entirely redundant: the data
it produces for known commits is immediately ignored by `INSERT OR IGNORE`.

## 3. Goals

- Read the set of already-stored commit SHAs for a repository through a new,
  **lightweight** driven port (a `SELECT sha FROM commit_facts WHERE repository_id = ?`,
  not a message/analysis load).
- Pass that skip-set into `CommitExtractor.extract_commits(skip_shas)`; the extractor
  **must not** compute `commit.stats` (the `git diff`) for a SHA in the skip-set.
- Keep the persisted commit facts and file facts **byte-identical** to the current
  full-extraction path for the same history (append-only; `INSERT OR IGNORE` semantics
  unchanged).
- Make "Refresh all" and re-paste/re-ingest cost proportional to the number of **new**
  commits, not the total history size.
- Degrade to today's behavior when the skip-set is empty or the reader is not wired
  (first-ever ingest, or a composition without the reader).

## 4. Non-goals

- **No orphan pruning.** When upstream rewrites history (rebase/force-push), commits
  previously stored whose SHAs no longer exist in the history are **kept** in the
  database (tolerated as orphans). Removing them is explicitly out of scope; a
  re-analyze or delete is the recovery path. Documented as a known limitation
  (ADR 010 style). This is the user-confirmed decision: "keep what is already there,
  add the new ones."
- **No change to analysis.** Ingest already never touches `commit_analysis`
  (facts/interpretations are separate, ADR 004). Analyzed commits stay analyzed; new
  commits land unanalyzed, ready for **+ Analyze** — same as today.
- **No concurrency.** "Refresh all" stays sequential (spec 028 non-goal).
- **No walk-level Git optimization** (e.g. `git rev-list --not`). The win comes from
  skipping the per-commit diff; enumerating commit metadata over the full history stays
  as-is (cheap relative to the diffs).

## 5. Users

- A local user running **Refresh all** (or re-pasting a repository URL) on repositories
  with substantial history, who currently waits far longer than the number of new
  commits justifies.

## 6. User stories

- As a user with several large tracked repositories, when I click **Refresh all** and
  nothing has changed upstream, it completes quickly instead of re-diffing every commit.
- As a user re-pasting a repository URL to pull a handful of new commits, the fetch +
  extract cost tracks the new commits only, and my already-analyzed commits are untouched.

## 7. Acceptance criteria

- **AC-01** Given a repository with commits already stored, when `ingest` runs and a
  `StoredCommitShaReader` is wired, then `extract_commits` is called with a skip-set equal
  to the stored SHAs for that `repository_id`.
- **AC-02** Given a SHA in the skip-set, when `extract_commits` runs, then `commit.stats`
  (the per-commit `git diff`) is **not** accessed for that commit and no `ExtractedCommit`
  is emitted for it.
- **AC-03** Given new commits not in the skip-set, when `extract_commits` runs, then each
  is emitted as an `ExtractedCommit` with its file changes, exactly as in full extraction.
- **AC-04** Given an incremental ingest, the `commit_facts` and `file_facts` rows for the
  repository are identical to what a full (empty-skip-set) ingest of the same history would
  produce — incremental extraction adds only new rows and removes none.
- **AC-05** Given an empty skip-set (first ingest) or no reader wired, `extract_commits`
  behaves exactly as today (full extraction), and existing ingest tests pass unchanged in
  behavior.
- **AC-06** `StoredCommitShaReader.read_stored_shas(repository_id)` returns the set of SHAs
  in `commit_facts` for that repository (empty set for an unknown repository), for both the
  SQLite and PostgreSQL adapters.
- **AC-07** The `IngestionResult.commits_inserted` count still reflects the number of new
  commits actually inserted; `commits_reused` remains a non-misleading, non-negative count
  (it MAY be reported as the size of the skip-set rather than a per-row writer tally).
- **AC-08** "Refresh all" over repositories with no new commits performs **zero**
  `commit.stats` / per-commit `git diff` computations (verified via a spy/extractor double).

## 8. Domain concepts

- **Skip-set**: the set of commit SHAs already persisted for a repository; the extractor
  treats membership as "already have it, do not re-diff".
- **Orphan commit**: a stored commit whose SHA no longer appears in the current history
  (after upstream history rewrite). Tolerated, not pruned (Non-goal §4).

## 9. Inputs and outputs

- **New port** `StoredCommitShaReader` (application/ports.py):
  `read_stored_shas(self, repository_id: str) -> set[str]`.
- **Extractor port change** `CommitExtractor.extract_commits(self, skip_shas: frozenset[str] = frozenset()) -> list[ExtractedCommit]`.
  Default preserves the no-arg call site and full-extraction behavior.
- **Adapters**: `SqliteStoredCommitShaReader` / `PostgresStoredCommitShaReader` backed by
  `SELECT sha FROM commit_facts WHERE repository_id = ?`.
- **Service wiring** (`application/service.py`): before extraction, if a
  `StoredCommitShaReader` is wired, read the skip-set and pass it to `extract_commits`.
- **Composition** (`composition.py`): build and inject the reader into the ingestion service
  (SQLite/Postgres selected by the existing backend seam).

## 10. Evidence requirements

- Not applicable to LLM claims (no narrative/interpretation change). The correctness
  evidence is the AC-04 equivalence test (incremental store == full store for the same
  history) and the AC-02/AC-08 no-diff-for-known-SHA spy tests.

## 11. Failure modes

- **Reader raises / DB unavailable**: the skip-set read must not abort ingest with a worse
  outcome than today. If the reader fails, degrade to full extraction (empty skip-set) — a
  slow-but-correct fallback, never a crash or a missed commit.
- **Corrupt/partial clone**: unchanged from today — handled upstream by `clone_or_fetch`
  and the extractor's existing per-commit `try/except` around `commit.stats`.
- **SHA in skip-set but absent from current history** (orphan): simply never encountered
  during the walk; no effect, no error (Non-goal §4).

## 12. Security considerations

- Repository content (SHAs, paths, diffs) remains untrusted input (CODEX §7). The new SQL
  is a parameterized read of an internal column (`sha`) filtered by `repository_id`; no
  user/LLM text enters the query. No new external surface, no new credentials.

## 13. Privacy considerations

- None. No new data collected or exposed; the skip-set is derived from already-stored SHAs.

## 14. Observability

- The existing per-repository refresh result already reports new-commit counts. Optionally
  log (debug) the skip-set size vs. new-commit count per ingest; no secrets, counts only.

## 15. Tests required

- Unit: `StoredCommitShaReader` SQLite adapter roundtrip (stored SHAs returned; empty set for
  unknown repo). Postgres adapter mirror, `DATABASE_URL`-gated (skips without it).
- Unit: `GitPythonCommitExtractor` skips `commit.stats` for skip-set members (spy on a fake
  commit whose `.stats` access raises → not raised when SHA is in skip-set; raised/consumed
  for new SHAs) and emits only new `ExtractedCommit`s.
- Unit: `RepositoryIngestionService` reads the skip-set and passes it to the extractor when
  the reader is wired; passes an empty skip-set (or preserves no-arg behavior) when unwired;
  AC-04 equivalence (incremental vs full produce the same stored rows).
- Unit: `RefreshAllService` / ingest with a no-new-commits repository performs zero
  `commit.stats` computations (AC-08, via extractor spy).

## 16. Evaluation required

- None (no LLM prompt or output change).

## 17. Documentation impact

- `docs/architecture.md` roadmap: add spec 030 (Implemented on completion).
- ADR 010 (accepted limitations): add the tolerated-orphan note (rebase/force-push leaves
  stale commits until re-analyze/delete), OR a short new ADR referencing it.
- `docs/progress/{pipeline|ingestion}/batch-{N}-incremental-commit-extraction.md` + README entry.

## 18. ADR impact

- Extends ADR 010's accepted-limitations list with the tolerated-orphan behavior. No new
  architectural pattern (the new port follows the existing driven-port + composition seam).

## 19. Open questions

- None blocking. `commits_reused` reporting (AC-07) may be set to the skip-set size; the exact
  value is informational and not user-critical.
