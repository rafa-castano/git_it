## Batch 157 — Verified file/folder path linking, tree-grounded (spec 029)

### Goal

Make case-study and chat file/folder links **correct** instead of optimistic. Spec 020 linked
every backtick-wrapped path span to `/blob|/tree/{branch}/{path}` without checking it exists, so a
bare basename the LLM wrote (`` `ports.py` ``) linked to the repo root and 404'd when the real file
is nested. Spec 029 grounds every link in the repository's real file tree: a span becomes a link
**only if the path actually exists** in the tree captured from the local clone; anything unverified
renders as plain code — never a broken link. This is the four slices of spec 029 bundled into one
commit (batch 157).

### What was added

**Slice 1 — tree capture + store (ingestion)**
- `FileTreeReader` / `FileTreeWriter` ports (`application/ports.py`).
- `GitPythonFileTreeReader` (`infrastructure/commits.py`): lists tracked paths via
  `git ls-tree -r --name-only <default_branch or HEAD>` against the same bare clone the service
  already owns — token-independent, no GitHub API call. Every path passes a safe-charset gate
  (`^[A-Za-z0-9._/-]+$`, no `..`, no leading `/`); every failure mode degrades to `[]` (never raises).
- `SqliteFileTreeStore` / `PostgresFileTreeStore` (new `sqlite/file_tree.py`, `postgres/file_tree.py`):
  table `repository_files` PK `(repository_id, path)`, **replace-on-write** (a tree is a snapshot,
  not an accumulating log). `migrations/001_initial.sql` gains the table.
- `build_file_tree_store()` factory + reader/writer wired into `RepositoryIngestionService.ingest()`
  under the same "clone_or_fetch succeeded" guard as default-branch capture, so **Refresh all**
  (spec 028) repopulates the tree for pre-existing repositories for free. Delete purges
  `repository_files` for both backends.

**Slice 2 — API (lazy per-repo)**
- `GET /api/repos/{repository_id}/file-paths` → `FilePathsResponse{paths: list[str]}`. Never 404s:
  a repo with no captured tree (pre-existing / never refreshed / unknown) returns `{"paths": []}`
  with 200. The homepage `GET /api/repos` list stays unchanged (the tree is repo-scoped and
  potentially large — it rides only on this lazy endpoint).

**Slice 3 — frontend tree-verified linking (`static/app.js`)**
- `_linkifyPaths(html, canonicalUrl, defaultBranch, filePathSet)` links a span only when it passes
  `isLinkablePath` (requires `/`) AND is tree-verified by `_verifyTreePath`: exact set membership →
  file (`/blob`), strict directory prefix of a member → folder (`/tree`). Visible text is the
  **basename** (`_pathBasename`); the full path goes in `title=` (both escaped via `esc()`).
  Guards return the HTML unchanged when the set is empty, the branch is unsafe, or the URL is not
  github.com (AC-07). SHA-linkify still runs first.
- Lazy fetch + per-repo cache (`_loadFilePathSet` / `_getFilePathSet` / `_filePathSetCache`); a
  failed/empty response caches an empty Set → no links, no error.

**Slice 4 — prompt + eval**
- Narrative (`_BASE_PROMPT` + `_BASE_INCREMENTAL_PROMPT`) and chat (`SYSTEM_PROMPT`) now instruct the
  model to write file references as **full repository-relative paths in backticks** (as shown in the
  provided file evidence), falling back to a bare filename only when the full path is unknown.
- `evals/file_path_linking_eval.py` (live-LLM, skips without an API key) asserts generated narratives
  reference in-context files as full paths (contain `/`), not bare basenames. Deterministic offline
  guard: prompt-text tests assert the instruction is present in both system prompts.

### Tests added

- New: `test_file_tree_reader.py`, `test_file_tree_store_sqlite.py`.
- Extended: `test_repository_ingestion_service.py` (reader/writer only after successful clone; never
  on `GitGatewayError`; unchanged when unwired), `test_postgres_adapters.py` (`PostgresFileTreeStore`
  roundtrip/replace, `DATABASE_URL`-gated), `test_api_repos.py` (endpoint returns stored paths / empty
  200 / list excludes paths), `test_api_delete.py` (delete removes tree rows), `test_api_static.py`
  (`_linkifyPaths` 4-arg signature, membership/prefix verification, basename + full-path title, lazy
  fetch/cache), `test_narrative_service.py` + `test_chat_service.py` (full-path instruction present).
- Full unit suite green: **1197 passed, 36 skipped** (Postgres tests skipped without `DATABASE_URL`).

### Gotchas

- **Reader uses `HEAD`, not a resolved branch name.** For a bare clone, `HEAD`'s symref already
  points at the default-branch tip, so `git ls-tree -r --name-only HEAD` lists exactly the
  default-branch tree — no extra default-branch-store read on the hot ingest path. The reader still
  accepts an explicit `default_branch`.
- **Empty snapshots are persisted.** Unlike default-branch capture (writes only when non-`None`), the
  tree writer runs whenever wired: a replace-on-write snapshot legitimately clears a prior snapshot.
- **Verification is confirmatory, never fuzzy.** The LLM supplies the full path; the tree only
  verifies exact membership (files) or prefix (folders). No basename-resolution guessing — two
  `service.py` are disambiguated by the LLM's own context, not by us. A path not in the tree stays
  plain code, so a crafted narrative cannot smuggle an arbitrary `/blob/...` target.
- **Pre-existing latent type error surfaced.** Bundling `test_narrative_service.py` into this commit
  tripped the pre-commit mypy-on-tests hook on a HEAD-existing `claim_type: str` vs
  `Literal[...]` mismatch in `_make_discussion_evidence`; fixed the annotation as part of this batch.

### Commits

- `feat: verified file/folder path linking grounded in repo file tree (spec 029)`
