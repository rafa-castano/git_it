# Batch 96 — File/folder path linking in narrative text (spec 020)

## Goal

Turn backtick-wrapped file/folder paths in case-study narratives (e.g.
`` `src/foo.py` ``, `` `tests/` ``) into clickable GitHub links, mirroring how
commit SHAs are already linkified. Building a correct `/blob/{branch}/...` URL
requires the repository's default branch, which ingestion did not capture
before this batch — so this batch also adds default-branch capture, sourced
from the local git clone (token-independent, no GitHub API call).

## Changes Made

### Application (`application/ports.py`, `application/service.py`)

- New `DefaultBranchReader` / `DefaultBranchWriter` protocols.
- `RepositoryIngestionService` gained two optional constructor ports
  (`default_branch_reader`, `default_branch_writer`), called right after a
  successful `clone_or_fetch` — same guard, same place as the existing
  optional `commit_extractor`. Never called on gateway failure; writer is
  only invoked when the reader resolves a value.

### Infrastructure — git reader (`infrastructure/commits.py`)

- `GitPythonDefaultBranchReader(cache_path)` — opens the bare clone with
  GitPython, returns `None` if `HEAD` is detached, otherwise
  `head.reference.name` filtered through a safe-charset check
  (`[A-Za-z0-9._/-]+`, no `..`, no leading/trailing `/`). Never raises —
  every failure mode degrades to `None`.

### Infrastructure — stores (`infrastructure/sqlite.py`, `infrastructure/postgres.py`)

- `SqliteDefaultBranchStore` / `PostgresDefaultBranchStore`: one upserted row
  per repository in a new `default_branch_metadata` table
  (`repository_id PK, default_branch TEXT NOT NULL, updated_at`).
- Deliberately a **new, independent table** from spec 019's `repo_metadata` —
  that table's `stars` column is `NOT NULL` because it is only ever written
  together with a successful, token-gated GitHub fetch. Default-branch
  capture must work with `GITHUB_TOKEN` unset, so folding it into
  `repo_metadata` would force loosening an unrelated, already-shipped
  contract.
- Both repository deleters updated to also purge `default_branch_metadata` on
  repo deletion.
- `migrations/001_initial.sql` — `default_branch_metadata` table added for
  Postgres.

### Composition (`composition.py`)

- `build_default_branch_store(*, project_root)` — mirrors
  `build_repo_metadata_store`'s backend-aware pattern.
- `build_repository_ingestion_service(...)` now also wires a real
  `GitPythonDefaultBranchReader` + the default-branch store, overridable via
  new optional keyword args (test seam, same pattern as `commit_extractor`).

### API (`api/schemas.py`, `api/routes/repos.py`)

- `RepoSummary.default_branch: str | None = None`.
- `GET /api/repos` reads the default-branch store per repository (same N+1
  posture already accepted for `repo_metadata` in spec 019) and populates the
  field, defaulting to `None` when no row exists.

### Frontend (`static/app.js`)

- `_linkifyPaths(html, canonicalUrl, defaultBranch)` — rewrites bare
  `<code>...</code>` spans (never `<pre><code>` fenced blocks, via a
  `(?<!<pre>)` guard) whose text passes `isLinkablePath`: no whitespace, safe
  charset, no `..`, no leading `/`, no `://`, and either contains a `/` or
  ends in one of a fixed extension list. Trailing `/` or no recognized
  extension → `/tree/` link; recognized extension → `/blob/` link.
- `isLinkablePath(text)` and `_pathToGithubUrl(path, canonicalUrl, branch)`
  kept as small, independently-callable pure functions.
- Wired into `loadCaseStudy` immediately **after** `_linkifyCommitShas` on the
  same HTML — see Gotchas for why this ordering is load-bearing, not
  cosmetic.

## Files Changed

- `specs/020-file-folder-path-linking.md` — new spec (Accepted)
- `src/git_it/repository_ingestion/application/ports.py` — `DefaultBranchReader`/`DefaultBranchWriter`
- `src/git_it/repository_ingestion/application/service.py` — optional port wiring in `ingest()`
- `src/git_it/repository_ingestion/infrastructure/commits.py` — `GitPythonDefaultBranchReader`
- `src/git_it/repository_ingestion/infrastructure/sqlite.py` — `SqliteDefaultBranchStore` + deleter update
- `src/git_it/repository_ingestion/infrastructure/postgres.py` — `PostgresDefaultBranchStore` + deleter update
- `migrations/001_initial.sql` — `default_branch_metadata` table
- `src/git_it/repository_ingestion/composition.py` — `build_default_branch_store`, ingestion service wiring
- `src/git_it/api/schemas.py` — `RepoSummary.default_branch`
- `src/git_it/api/routes/repos.py` — `list_repos` wiring
- `src/git_it/static/app.js` — `_linkifyPaths`, `isLinkablePath`, `_pathToGithubUrl`, `_isFolderPath`, `loadCaseStudy` wiring
- `tests/unit/test_default_branch_reader.py` — new (6 tests)
- `tests/unit/test_repository_ingestion_service.py` — 4 new tests
- `tests/unit/test_default_branch_store_sqlite.py` — new (5 tests)
- `tests/unit/test_postgres_adapters.py` — 3 new tests (skipped without live Postgres)
- `tests/unit/test_api_repos.py` — 2 new tests
- `tests/unit/test_api_delete.py` — 1 new test
- `docs/progress/ingestion/batch-96-file-folder-path-linking.md` — this file
- `docs/progress/README.md` — new entry in Ingestion section

## Tests Added

21 new tests (18 unconditional + 3 Postgres-gated, skipped locally without
`DATABASE_URL`):

- `test_default_branch_reader.py` (6): reads branch from a real bare-clone
  fixture; reads a non-`main` branch name; detached HEAD → `None` (simulated
  by rewriting the bare clone's `HEAD` file to a raw SHA); unsafe branch name
  → `None` (HEAD rewritten to `ref: refs/heads/weird;rm -rf`); branch name
  containing `..` → `None`; non-existent clone path → `None` without raising.
- `test_repository_ingestion_service.py` (+4): reader/writer called after a
  successful clone with the resolved branch persisted; writer not called when
  the reader returns `None`; behavior unchanged when neither port is wired;
  reader/writer never called on a `GitGatewayError`.
- `test_default_branch_store_sqlite.py` (5): roundtrip, upsert overwrite,
  cross-repo independence, `initialize()` idempotency, absent-row read.
- `test_postgres_adapters.py` (+3, skipped without `DATABASE_URL`): absent
  read, roundtrip, upsert overwrite.
- `test_api_repos.py` (+2): `default_branch` absent by default; populated
  when stored.
- `test_api_delete.py` (+1): deleting a repository also removes its
  `default_branch_metadata` row.

Full suite: 795 passed, 18 skipped (was 777 passed / 15 skipped before this
batch — 18 new unconditional tests + 3 new Postgres-gated tests).

Quality gates: `ruff check .` (all checks passed), `ruff format --check .`
(141 files already formatted), `mypy src/` (no issues, 50 source files),
`node --check src/git_it/static/app.js` (OK).

## Gotchas

- **New table, not an extension of spec 019's `repo_metadata`.** Considered
  folding `default_branch` into the existing stars/languages table since both
  are "repo-level GitHub-adjacent metadata," but `repo_metadata.stars` is
  `NOT NULL` and only ever written alongside a successful, token-gated fetch.
  Default-branch capture must work with `GITHUB_TOKEN` unset, so it needed
  either a nullable-`stars` schema change to an already-shipped, already-tested
  contract, or a new table. Chose the new table — smaller blast radius, zero
  risk to spec 019's existing tests.
- **Capture lives inside `RepositoryIngestionService`, not the route-level
  `_ingest_bg`.** This is the opposite placement from spec 019's GitHub
  stars/languages fetch, which deliberately lives in `_ingest_bg` because it's
  a GitHub API concern the ingestion service doesn't otherwise have. Default
  branch capture is pure git (reading `HEAD` from the clone the service
  already owns), so it uses the same optional-port pattern the service
  already has for commit extraction.
- **Ordering between the two linkifiers is load-bearing, not cosmetic.**
  `_linkifyPaths` must run after `_linkifyCommitShas` on the same HTML.
  Verified with an ad-hoc Node script (not checked in — no JS test framework
  in this repo, confirmed absent same as specs 016-019) that reversing the
  order would let the SHA-linkifier's bare-hex regex match visible text
  nested inside an already-built `<a href="...blob...">`, producing a broken
  nested anchor.
- **Accepted narrow edge case surfaced by that same verification:** a path
  whose name is itself a pure 7-40-character hex string (e.g.
  `src/deadbeef.py`) gets a `commit/<hex>` link burned into it by
  `_linkifyCommitShas` before `_linkifyPaths` ever sees the span; the span
  then fails path-linking's `[^<]*` content-purity check and keeps the (still
  harmless, non-broken) commit link instead of a blob link. No corruption —
  verified no nested/malformed anchors — just a missed blob link for an
  extremely rare filename shape. Documented in spec 020's Failure modes
  rather than "fixed," since fixing it would mean teaching the existing,
  unrelated `_linkifyCommitShas` about `<code>` boundaries — out of scope for
  this batch.
- **Re-fetch does not refresh `HEAD`.** A subsequent ingestion of an
  already-cloned repository runs `git fetch`, not `git clone` — `git fetch`
  does not update the local bare repo's `HEAD` symref. If a repository's
  default branch changes on GitHub after first ingestion, Git It's stored
  value can go stale. Accepted (documented as an open question in the spec);
  same "fetch once" posture spec 019 already established for stars/languages.
- **JS test framework:** none exists in this repo (confirmed absence, same as
  specs 016/017/018/019) — `node --check` plus the throwaway Node
  verification script (scratch-only, not committed) were the available gates;
  manual/e2e verification steps are listed in the spec for the orchestrator
  to run via Playwright.

## Commits

- (recorded in the batch commit for this file)
