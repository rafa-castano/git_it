# Spec 029: Verified File/Folder Path Linking (Tree-Grounded)

**Status:** Implemented
**Spec number:** 029
**Author:** Rafael Castaño
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: Architecture Agent, Security Agent, Quality Agent
Created: 2026-07-08
Updated: 2026-07-08

## 1. Summary

Spec 020 turned backtick-wrapped file/folder spans in case-study and chat HTML
into GitHub `/blob|/tree/{branch}/{path}` links **optimistically** — it never
verified the path exists in the repository (an explicit Non-goal of spec 020,
§4/§19). In practice the narrative LLM frequently emits a **bare basename**
(e.g. `` `ports.py` ``), which spec 020 links to `/blob/{branch}/ports.py` at
the repo root — a 404 when the real file is nested
(`src/git_it/repository_ingestion/application/ports.py`).

This spec makes those links **correct** by grounding them in the repository's
real file tree:

1. The narrative/chat LLM is prompted to write file references as **full
   repository-relative paths** in backticks (it already has full paths for the
   hotspot files injected into its context).
2. Git It **captures the repository's file tree** at ingestion (and refresh),
   read directly from the local bare clone via `git ls-tree` — token-independent,
   the same placement and untrusted-input posture as spec 020's default-branch
   capture.
3. The frontend links a path span **only if that path actually exists** in the
   captured tree (a file must match a tree entry exactly; a folder must be a
   real directory prefix of some entry). Anything unverified renders as plain
   code — **never a broken link**. The link's visible text is shortened to the
   **basename**, with the full path shown in the `title` tooltip.

The net effect: file links either point at the real file on GitHub or are not
links at all. This upgrades spec 020's "link optimistically" posture to the
evidence-grounded, no-hallucinated-links posture CODEX.md requires.

## 2. Problem

A learner reading the git_it case study clicks `` `ports.py` `` and lands on a
GitHub 404, because the LLM wrote the basename and spec 020 linked it to the
repo root. Every file link that isn't already a full, correct path is either
broken or points somewhere misleading. A link to a path that does not exist is
exactly the kind of unsupported, un-evidenced claim CODEX.md §1/§3 forbids.

## 3. Goals

- Prompt the narrative (`narrative_service.py`) and chat (`chat/service.py`)
  LLMs to reference files as **full repository-relative paths** in backticks,
  grounded in the file evidence already available to them, and to fall back to
  a bare filename only when the full path is genuinely unknown.
- Capture each repository's **file tree** (the set of tracked file paths at the
  default branch tip) once at ingestion, read from the local bare clone via
  `git ls-tree -r --name-only <default_branch>` — no GitHub API call, works with
  `GITHUB_TOKEN` unset.
- Persist the file tree in a **new store**, wired through the existing
  `_get_db_backend()` / `build_*` composition pattern (SQLite + PostgreSQL),
  and remove it on repository delete.
- Populate the tree for **already-ingested repositories** through the existing
  **Refresh all** action (spec 028) / any re-ingest — no dedicated backfill
  endpoint.
- Expose the repository's file paths to the frontend through a **lazy,
  per-repository** API (not on the `GET /api/repos` homepage list).
- Rewrite a backtick-wrapped path span into a link **only when the path is
  verified** against the captured tree; render the **basename** as the visible
  text and the **full path** in the `title`. Leave every unverified span as
  plain code.

## 4. Non-goals

- Free-text (non-backtick) path detection — unchanged from spec 020 §4.
- Fuzzy/basename resolution against the tree (e.g. "there is exactly one
  `ports.py`, link it"): rejected. The **LLM supplies the full path**; the tree
  only **verifies** it. This avoids ambiguity entirely (two `service.py` are
  disambiguated by the LLM's own context, not guessed) and keeps the tree's
  role purely confirmatory. (See Open questions for a possible future fallback.)
- Verifying line ranges / anchors within a file — only file/folder existence.
- A scheduled tree refresh independent of ingest/refresh.
- Changing spec 019 (`repo_metadata`) or spec 020 (`default_branch_metadata`)
  stores — this is a new, independent store.
- Introducing any new external dependency — `git ls-tree` runs through the
  existing git access path.

## 5. Users

- **Learner**: reading a case study or chatting with GitItGPT, wants a file
  reference to be a link that opens the **real** file on GitHub, and to never
  land on a 404.

## 6. User stories

```md
As a learner reading a case study that mentions the ports module,
I want the `ports.py` reference to link to the real file
(src/git_it/repository_ingestion/application/ports.py) on GitHub,
so that I can inspect the actual code and never hit a 404.
```

```md
As a maintainer who already ingested a repository before this feature,
I want clicking "Refresh all" to capture the file tree,
so that verified file links start working without a full re-clone.
```

## 7. Acceptance criteria

### AC-01 — File tree captured from the local clone, token-independent

```gherkin
Given RepositoryIngestionService.ingest() completes clone_or_fetch successfully
And a FileTreeReader and FileTreeWriter are wired
When ingest() runs
Then the reader lists tracked file paths at the resolved default branch tip
  from the local bare clone (git ls-tree -r --name-only)
And the writer persists them keyed by repository_id
And no HTTP call is made and no GITHUB_TOKEN is required
```

### AC-02 — Unsafe or unresolvable entries are dropped, never persisted

```gherkin
Given a listed path contains characters outside [A-Za-z0-9._/-], or "..",
  or starts with "/"
When the file tree reader runs
Then that path is excluded from the captured set
And only the safe remainder is persisted
```

(Repository content is untrusted input, CODEX.md §7 — the same safe-charset
gate spec 020 applies to branch names is applied per path here.)

### AC-03 — Clone/fetch failure → reader never runs

```gherkin
Given git_gateway.clone_or_fetch raises GitGatewayError
When ingest() runs
Then the file tree reader is never called
And behavior is unchanged when the file-tree ports are not wired
```

### AC-04 — Refresh repopulates the tree for existing repositories

```gherkin
Given a repository ingested before this feature has no stored file tree
When it is refreshed via the Refresh all action (spec 028) / re-ingest
Then ingest() captures and persists its file tree
```

### AC-05 — API exposes a repository's file paths lazily

```gherkin
Given a repository has a stored file tree
When GET /api/repos/{repository_id}/file-paths is called
Then it returns the list of verified-safe file paths for that repository

Given a repository has no stored file tree (pre-existing, not yet refreshed)
When GET /api/repos/{repository_id}/file-paths is called
Then it returns an empty path list (200), not an error
And GET /api/repos (homepage list) does NOT include the file paths
```

### AC-06 — Frontend links only tree-verified paths, shows the basename

```gherkin
Given the repository's file path set contains
  "src/git_it/repository_ingestion/application/ports.py"
And rendered HTML contains an inline
  <code>src/git_it/repository_ingestion/application/ports.py</code> span
When _linkifyPaths runs
Then that span becomes a link to
  {canonical_url}/blob/{default_branch}/src/git_it/repository_ingestion/application/ports.py
And the link's visible text is the basename "ports.py"
And the link's title attribute is the full path

Given rendered HTML contains an inline <code>ports.py</code> span
And no file path in the set equals "ports.py"
When _linkifyPaths runs
Then the span is left as plain code (no link)

Given rendered HTML contains an inline <code>tests/</code> span
And at least one file path in the set starts with "tests/"
When _linkifyPaths runs
Then that span links to {canonical_url}/tree/{default_branch}/tests/
  with visible text "tests/"

Given rendered HTML contains an inline <code>src/nope.py</code> span
And no file path equals "src/nope.py" and none starts with "src/nope.py/"
When _linkifyPaths runs
Then the span is left as plain code (no link)
```

### AC-07 — No file path set, or no default branch, or no GitHub URL → no linking

```gherkin
Given the repository's file path set is empty, OR defaultBranch is null/empty/
  unsafe, OR canonicalUrl is not a github.com URL
When _linkifyPaths runs
Then the HTML is returned unchanged (plain code spans, no links)
```

### AC-08 — Delete removes the file tree

```gherkin
Given a repository has a stored file tree
When the repository is deleted
Then its file-tree rows are removed along with its other data
```

### AC-09 — Narrative/chat prompt requests full paths

```gherkin
Given the narrative and chat system prompts
Then they instruct the model to reference files as full repository-relative
  paths in backticks (as shown in the provided file evidence), and to use a
  bare filename only when the full path is unknown
And an eval asserts generated file references are full paths (contain "/")
  rather than bare basenames, for files whose full path is in the provided
  context
```

## 8. Domain concepts

- **`FileTreeReader`** (new port, `application/ports.py`):
  `read_file_paths() -> list[str]`. Implemented by
  `GitPythonFileTreeReader` (`infrastructure/commits.py`, alongside
  `GitPythonCommitExtractor` / `GitPythonDefaultBranchReader` — same bare clone):
  lists `git ls-tree -r --name-only <default_branch or HEAD>`, applies the
  safe-charset filter per entry, returns the safe subset. Never raises — every
  failure mode degrades to `[]`.
- **`FileTreeWriter`** (new port): `save_file_paths(repository_id, paths) -> None`.
- **`SqliteFileTreeStore` / `PostgresFileTreeStore`** (new stores): table
  `repository_files` with PK `(repository_id, path)`, replace-on-write per
  repository (delete existing rows for the repo, insert the new set — a tree is
  a snapshot, not an accumulating log). New, independent table (same rationale
  as spec 020: keep contracts independent and reversible).
- **`build_file_tree_store()`** (new factory, `composition.py`): backend-aware,
  `.initialize()` for SQLite; mirrors `build_default_branch_store()`.
- **Capture placement (locked decision)**: inside
  `RepositoryIngestionService.ingest()`, as two new optional ports
  (`file_tree_reader`, `file_tree_writer`), under the same "clone_or_fetch
  succeeded" guard as commit extraction and default-branch capture. Pure git,
  same local clone the service already owns — belongs in the service, not the
  route layer. Refresh-all (spec 028) calls `ingest()`, so it repopulates the
  tree for existing repositories for free (AC-04).
- **API (locked decision)**: a dedicated `GET /api/repos/{id}/file-paths`
  returning `{ "paths": [...] }`, fetched **lazily** when a repository is opened
  (cached client-side per repo), keeping the homepage `GET /api/repos` payload
  unchanged. The file tree is repo-scoped and potentially large, so it must not
  ride on the list endpoint.
- **Verification + display (frontend, locked decision)**:
  `_linkifyPaths(html, canonicalUrl, defaultBranch, filePathSet)` gains the tree
  set. A backtick span's text is linkable only when it (a) passes the existing
  safe path-plausibility heuristic AND (b) is verified: a **file** span must be
  an exact member of `filePathSet`; a **folder** span (trailing `/`, or a span
  that is a strict directory prefix of some member) must prefix at least one
  member. The link's **visible text is the basename** (last non-empty segment);
  the **full path** goes in `title=` (escaped via `esc()`).
- **Prompt (locked decision)**: `narrative_service.py` and `chat/service.py`
  system prompts instruct full repo-relative paths in backticks, referencing the
  file evidence already in context (Hotspot Files inject full `file_path`
  values — `narrative_service.py:585`). No new per-commit file-path injection in
  this slice (see Open questions).

## 9. Inputs and outputs

New/changed public interfaces:

- `FileTreeReader.read_file_paths() -> list[str]` (port)
- `FileTreeWriter.save_file_paths(repository_id: str, paths: list[str]) -> None` (port)
- `GitPythonFileTreeReader(cache_path, default_branch)` — `read_file_paths()`
- `SqliteFileTreeStore(database_path).initialize()/.save_file_paths(...)/.get_file_paths(repository_id) -> list[str]`
- `PostgresFileTreeStore(conninfo)` — same contract
- `build_file_tree_store(*, project_root)`
- `RepositoryIngestionService.__init__(..., file_tree_reader=None, file_tree_writer=None)`
- `GET /api/repos/{repository_id}/file-paths -> {"paths": list[str]}` (`api/routes/repos.py`, `api/schemas.py`)
- Frontend: `_linkifyPaths(html, canonicalUrl, defaultBranch, filePathSet)`;
  a per-repo fetch+cache of the path set on repo open.

## 10. Evidence requirements

The file tree is a raw git fact (tracked paths at the branch tip), not an LLM
interpretation. Its whole purpose here is to **enforce** evidence-grounding: a
file link is only rendered when the path is confirmed to exist. The LLM-emitted
full path is the candidate; the tree is the evidence that authorizes the link.

## 11. Failure modes

| Failure | Behavior |
|---|---|
| `clone_or_fetch` fails | File tree reader never runs (AC-03). |
| `git ls-tree` raises / clone corrupt | Reader returns `[]` (caught internally). |
| A listed path fails the safe-charset gate | Excluded from the captured set (AC-02). |
| Repository has no stored tree (pre-existing, not refreshed) | API returns `{"paths": []}`; frontend renders no path links, only plain code (AC-05, AC-07). |
| LLM emits a full path not in the tree (slightly wrong / hallucinated) | Span left as plain code — **no broken link** (AC-06). |
| LLM emits a bare basename | Not an exact member → plain code (AC-06). Improves once the prompt lands (AC-09). |
| `default_branch` is null/unsafe or `canonical_url` not GitHub | No linking at all (AC-07). |
| A path segment is a 7–40 char pure-hex string | Same accepted, documented interaction as spec 020 §11 (SHA-linkify runs first). Now additionally: even if linked, only verified paths survive. |

## 12. Security considerations

- **Untrusted paths**: every path from `git ls-tree` is repository content →
  filtered against the fixed safe charset (`[A-Za-z0-9._/-]`, no `..`, no
  leading `/`) before it is persisted, returned by the API, or used to build a
  URL. The frontend re-validates the same charset before interpolating into a
  URL (defense in depth, matching spec 020).
- **Membership check is exact**: file links require an exact set-membership
  match, so a crafted narrative cannot smuggle an arbitrary `/blob/...` target
  unless that exact path is a real, safe tree entry.
- **Display shortening does not weaken escaping**: the basename shown and the
  full path in `title=` are both passed through the existing `esc()` helper.
- **Ordering unchanged**: SHA-linkify still runs before path-linkify. (Batch 156
  already made `_linkifyCommitShas` tag-aware, so it no longer corrupts
  attributes; path-linkify continues to operate only on pure `<code>` spans.)
- **Payload**: the file path set is public repository metadata (visible on
  GitHub); no new personal data. The lazy per-repo endpoint avoids shipping
  every repo's tree on the homepage.

## 13. Privacy considerations

File paths are already-public repository metadata. No new personal data is
collected, logged, or transmitted.

## 14. Observability

- No new logging beyond the existing broad ingest error handling —
  `GitPythonFileTreeReader` never raises. Consider (non-blocking) a debug count
  of captured paths per repository.

## 15. Tests required

### Automated tests (pytest, TDD — failing first)

- `tests/unit/test_file_tree_reader.py` (new): lists paths from a real local
  bare-clone fixture (mirrors `test_default_branch_reader.py`); nested paths
  returned with full relative path; unsafe entries filtered; corrupt/missing
  clone returns `[]` without raising.
- `tests/unit/test_repository_ingestion_service.py` (extended): file-tree
  reader/writer called only after a successful `clone_or_fetch`; writer invoked
  with the safe path set keyed by `repository_id`; never called on
  `GitGatewayError`; unchanged behavior when the ports are not wired.
- `tests/unit/test_file_tree_store_sqlite.py` (new): insert + read roundtrip,
  replace-on-write overwrites the previous snapshot, unknown repo returns `[]`,
  distinct repositories independent, `initialize()` idempotent.
- `tests/unit/test_postgres_adapters.py` (extended): `PostgresFileTreeStore`
  roundtrip + replace, gated by the existing `DATABASE_URL` skip.
- `tests/unit/test_api_repos.py` (extended): `GET /api/repos/{id}/file-paths`
  returns the stored paths; empty list when absent; the homepage `GET /api/repos`
  does NOT include file paths.
- `tests/unit/test_api_delete.py` (extended): deleting a repository removes its
  file-tree rows.
- `tests/unit/test_api_static.py` (extended, source-string convention): the
  served `app.js` `_linkifyPaths` (a) takes a file-path set, (b) requires exact
  membership for files / prefix match for folders, and (c) renders the basename
  as visible text with the full path in `title=`.

### Manual/e2e verification (Playwright, orchestrator)

1. Refresh git_it, open its case study: a full-path reference links to the real
   nested file on GitHub (HTTP 200), shows the basename, full path on hover.
2. A basename with no matching tree entry renders as plain code (no link).
3. A folder reference (`tests/`) links to `/tree/{branch}/tests/`.
4. Commit-SHA links elsewhere still work (no corruption running both linkifiers).

### Evaluation required

- `evals/` (new/extended): assert generated narratives reference files whose
  full path is in the provided context as **full paths** (contain `/`), not
  bare basenames; assert no banned "root basename" pattern for such files.

## 16. Documentation impact

- Progress docs per slice under `docs/progress/{ingestion|api|ui}/`.
- `docs/progress/README.md` entries.
- `docs/architecture.md` roadmap: add spec 029; note it supersedes spec 020's
  "link optimistically" posture with tree-verified linking.
- README "Everyday use": note that file links in case studies point at real
  files and that a **Refresh all** populates the tree for older repositories.

## 17. ADR impact

None expected. Additive port + store + API field + prompt + frontend rendering
within the existing hexagonal layering, reusing spec 020's optional-port capture
pattern. If shipping the whole path set to the client proves too heavy for very
large repositories and we move verification server-side, that WOULD be an ADR —
tracked as an Open question, not adopted now.

## 18. Open questions

- **Inject a fuller file inventory into the narrative prompt?** The LLM reliably
  knows only hotspot file paths today. Injecting the full file list (or per-commit
  paths) would raise full-path accuracy (more links survive verification) at a
  token cost. Assumption for slice 1: rely on hotspots + verification; measure
  the unlinked-span rate via the eval before adding inventory.
- **Server-side verification for very large repos?** Shipping the whole path set
  to the client is fine for typical repos; a repo with tens of thousands of
  files may warrant server-side resolution (return the narrative pre-linkified,
  or a filtered set of only the paths mentioned). Deferred; would be an ADR.
- **Fuzzy fallback when the LLM path is close but wrong?** Explicitly out of
  scope now (Non-goal §4). Could later, if the LLM's full path is not in the
  tree, attempt a unique-basename/suffix resolution as a *secondary* verified
  candidate — still tree-grounded, still no 404.

## 19. Out of scope

- Free-text path detection; line-anchor linking; scheduled tree refresh;
  changes to spec 019/020 stores; a dedicated tree-backfill endpoint (Refresh
  all covers it); a JS unit-test framework (same absence as specs 016–020).

## 20. Proposed slices

1. **Tree capture + store** (ingestion): `FileTreeReader/Writer` ports,
   `GitPythonFileTreeReader`, `Sqlite/PostgresFileTreeStore`,
   `build_file_tree_store()`, wire into `ingest()`, delete cleanup. (AC-01–04,
   AC-08)
2. **API** : `GET /api/repos/{id}/file-paths` + schema. (AC-05)
3. **Frontend**: lazy per-repo fetch + cache; `_linkifyPaths` gains the set,
   verifies membership/prefix, renders basename + `title`. (AC-06–07)
4. **Prompt + eval**: full-path instruction in narrative + chat prompts; eval
   asserting full-path emission. (AC-09)
