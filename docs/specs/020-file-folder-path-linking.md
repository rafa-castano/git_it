# Spec 020: File/Folder Path Linking in Narrative Text

Status: Accepted
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: Architecture Agent, Security Agent, Quality Agent
Created: 2026-07-03
Updated: 2026-07-03

## 1. Summary

Case study narratives (spec 010) and chat replies frequently reference file and
folder paths (e.g. `` `src/git_it/api/routes/repos.py` ``, `` `tests/` ``) as
backtick-wrapped inline code spans, mirroring how commit SHAs are already
linkified (batch "Fix 6", `_linkifyCommitShas`). This spec makes those
backtick-wrapped path-like spans clickable links to the corresponding file or
folder on GitHub (`/blob/{branch}/{path}` or `/tree/{branch}/{path}`), reusing
the exact rendering point where SHA-linkification already runs.

Building a correct `/blob/{branch}/...` URL requires knowing the repository's
default branch, which Git It does not capture today. This spec also adds
default-branch capture, sourced from the local git clone during ingestion
(token-independent), persisted in a new store, and exposed on `GET /api/repos`
(the same response `currentRepoMeta` is already populated from).

## 2. Problem

A learner reading a case study narrative sees paths like `` `src/foo.py` ``
rendered as plain inline code — there is no way to jump straight to that file
on GitHub without manually navigating there. This is the same at-a-glance
navigability gap spec 019 closed for stars/languages, applied to in-narrative
file/folder references.

## 3. Goals

- Capture each repository's default branch once, at ingestion time, from the
  local bare clone's `HEAD` — no GitHub API call, works with `GITHUB_TOKEN`
  unset.
- Persist the captured default branch in a new store, wired through the
  existing `_get_db_backend()` / `build_*` composition pattern (SQLite +
  PostgreSQL).
- Expose `default_branch: str | None` on `RepoSummary` (`GET /api/repos`),
  populating the frontend's `currentRepoMeta`.
- Rewrite ONLY backtick-wrapped, path-plausible inline `<code>` spans in
  rendered case-study/chat HTML into links to
  `{canonical_url}/blob/{default_branch}/{path}` (files) or
  `{canonical_url}/tree/{default_branch}/{path}` (folders).
- Never linkify free-running text, fenced code blocks, or text already inside
  an anchor tag.

## 4. Non-goals

- Free-text path detection outside of backtick-wrapped spans (explicitly
  rejected — too many false positives, e.g. prose mentioning "the src
  directory").
- Verifying the path actually exists in the repository's file tree — paths
  are linked optimistically, exactly like SHA-linking does not verify the SHA
  exists.
- Refreshing the default branch on a schedule, or backfilling it for
  repositories ingested before this batch.
- Any change to `GithubRepoMetadataFetcher` / `RepoMetadata` (spec 019) — this
  is a new, independent store, not an extension of the stars/languages table.
- A generic "detect any GitHub entity in text" mechanism — only file/folder
  paths are in scope.

## 5. Users

- Learner: reading a case study narrative or chatting with GitItGPT, wants to
  jump straight to a referenced file/folder on GitHub without leaving Git It
  or manually constructing the URL.

## 6. User stories

```md
As a learner reading a case study narrative that mentions `src/foo.py`,
I want that path to be a clickable link to the file on GitHub,
so that I can inspect the real code without manually navigating there.
```

## 7. Acceptance criteria

### AC-01 — Default branch captured from the local clone, not the GitHub API

```gherkin
Given RepositoryIngestionService.ingest() completes clone_or_fetch successfully
And a DefaultBranchReader and DefaultBranchWriter are wired
When ingest() runs
Then the reader reads HEAD's symbolic reference from the local bare clone
And, if a safe branch name is resolved, the writer persists it keyed by
  repository_id
And no HTTP call is made and no GITHUB_TOKEN is required
```

### AC-02 — Detached HEAD or unresolvable ref → nothing persisted

```gherkin
Given the local clone's HEAD is detached (points directly to a commit, not a
  branch) or otherwise cannot be resolved
When the default branch reader runs
Then it returns None
And nothing is written to the default-branch store for this ingestion
```

### AC-03 — Unsafe branch name → nothing persisted

```gherkin
Given HEAD resolves to a ref whose short name contains characters outside
  [A-Za-z0-9._/-], contains "..", or starts/ends with "/"
When the default branch reader runs
Then it returns None
And nothing is written to the default-branch store
```

This is defense in depth: git itself refuses to create such ref names through
normal porcelain commands, but HEAD's target is read as raw ref-file text, so
the reader does not trust it blindly (CODEX.md: treat repository content as
untrusted input).

### AC-04 — Clone/fetch failure → reader never runs

```gherkin
Given git_gateway.clone_or_fetch raises GitGatewayError
When ingest() runs
Then the default branch reader is never called
```

### AC-05 — API exposes default_branch, absent when not captured

```gherkin
Given a repository has a stored default branch "main"
When GET /api/repos is called
Then the matching RepoSummary has default_branch == "main"

Given a repository has no row in the default-branch store (pre-existing
  repository, or HEAD could not be resolved at ingestion time)
When GET /api/repos is called
Then the matching RepoSummary has default_branch == None
```

### AC-06 — Frontend links only backtick-wrapped, path-plausible code spans

```gherkin
Given canonicalUrl includes "github.com" and defaultBranch is a non-empty
  string
And rendered HTML contains an inline `<code>src/foo.py</code>` span
When _linkifyPaths runs
Then that span becomes
  `<a href="{canonicalUrl}/blob/{defaultBranch}/src/foo.py" ...>src/foo.py</a>`

Given rendered HTML contains an inline `<code>tests/</code>` span
When _linkifyPaths runs
Then that span links to `{canonicalUrl}/tree/{defaultBranch}/tests/`

Given rendered HTML contains an inline `<code>True</code>` span (no slash, no
  recognized file extension)
When _linkifyPaths runs
Then that span is left unchanged

Given rendered HTML contains a fenced code block
  `<pre><code>...</code></pre>`
When _linkifyPaths runs
Then its content is left unchanged, regardless of what it contains
```

### AC-07 — No canonical GitHub URL or no default branch → no linking

```gherkin
Given canonicalUrl does not include "github.com", OR defaultBranch is null/
  empty/unsafe
When _linkifyPaths runs
Then the HTML is returned unchanged (no partial/broken links)
```

### AC-08 — SHA-linking and path-linking do not corrupt each other

```gherkin
Given _linkifyCommitShas has already run on the HTML (producing
  `<a href=".../commit/<sha>">...</a>` for bare hex tokens outside of href
  attributes)
When _linkifyPaths subsequently runs on that same HTML
Then it does not double-link, nest anchors, or break any existing anchor
And this ordering (SHA-linking always before path-linking) is the only
  supported order
```

## 8. Domain concepts

- **`DefaultBranchReader`** (new protocol, `application/ports.py`):
  `read_default_branch() -> str | None`. Implemented by
  `GitPythonDefaultBranchReader` (`infrastructure/commits.py`, alongside
  `GitPythonCommitExtractor` since both open the same bare clone via
  GitPython): opens `git.Repo(cache_path)`, returns `None` if `HEAD` is
  detached or resolution raises, otherwise returns `head.reference.name` if it
  passes the safe-charset check, else `None`. Never raises — every failure
  mode degrades to `None`, matching the "no branch -> no linking" acceptable
  degradation.
- **`DefaultBranchWriter`** (new protocol, `application/ports.py`):
  `save_default_branch(repository_id: str, default_branch: str) -> None`.
- **`SqliteDefaultBranchStore` / `PostgresDefaultBranchStore`** (new stores,
  `infrastructure/sqlite.py` / `infrastructure/postgres.py`): one row per
  repository (`repository_id` primary key), upserted, table
  `default_branch_metadata`. Deliberately a **new, independent table** from
  spec 019's `repo_metadata` (stars/languages) rather than an extension of it:
  `repo_metadata.stars` is `NOT NULL` because it is only ever written
  together with a successful GitHub stars fetch; default-branch capture must
  work with `GITHUB_TOKEN` unset, so folding it into that table would force
  loosening an already-shipped, already-tested NOT NULL invariant for an
  unrelated concern. A new table keeps both features' contracts independent
  and reversible.
- **`build_default_branch_store()`** (new factory, `composition.py`): mirrors
  `build_repo_metadata_store()` — backend-aware, calls `.initialize()` for
  SQLite.
- **Where default-branch capture happens (locked decision)**: inside
  `RepositoryIngestionService.ingest()` itself, as two new optional
  constructor ports (`default_branch_reader`, `default_branch_writer`), called
  in the same place and under the same "clone_or_fetch succeeded" guard as the
  existing optional `commit_extractor`/`commit_fact_writer`. This is the
  opposite placement decision from spec 019's GitHub stars/languages fetch
  (which lives in the route-level `_ingest_bg`, specifically because it is a
  GitHub API concern the ingestion service does not otherwise have). Default
  branch capture is pure git — reading `HEAD` from the same local clone the
  service already owns — so it belongs inside the service, not bolted on at
  the route layer.
- **Safe branch-name charset**: `[A-Za-z0-9._/-]+`, no `..`, must not start or
  end with `/`. Applied on the backend when capturing (reject and store
  nothing) and re-applied on the frontend before using `defaultBranch` to
  build a URL (defense in depth against any future backend regression).
- **Path-plausibility heuristic (frontend, locked decision)**: a backtick
  code-span's text is linkable when it has no whitespace, matches
  `[A-Za-z0-9._/-]+`, contains no `..`, does not start with `/`, does not
  contain a URL scheme (`://` anywhere, or `scheme://` prefix), and either
  contains a `/` or ends in one of a fixed extension list (`.py .ts .tsx .js
  .md .json .toml .yml .yaml .css .html .sql .txt .cfg .ini .sh`). Folder vs.
  file: trailing `/`, or no recognized extension, renders a `/tree/` link;
  a recognized extension renders a `/blob/` link.
- **Rendering integration point**: `_linkifyPaths(html, canonicalUrl,
  defaultBranch)` in `app.js`, called immediately after
  `_linkifyCommitShas(html, canonicalUrl)` in `loadCaseStudy` (same place both
  already run today for SHA-linking). SHA-linking must run first — see
  Security considerations for why the reverse order is unsafe.
- **8-and-under helper split**: `isLinkablePath(text)` (pure predicate) and
  `_pathToGithubUrl(path, canonicalUrl, branch)` (pure URL builder) are kept
  as small standalone functions so their logic is unit-inspectable even
  without a JS test framework (see Tests required).

## 9. Inputs and outputs

New/changed public interfaces:

- `DefaultBranchReader.read_default_branch() -> str | None` (port)
- `DefaultBranchWriter.save_default_branch(repository_id: str, default_branch: str) -> None` (port)
- `GitPythonDefaultBranchReader(cache_path: Path).read_default_branch() -> str | None`
- `SqliteDefaultBranchStore(database_path).initialize()/.save_default_branch(...)/.get_default_branch(repository_id) -> str | None`
- `PostgresDefaultBranchStore(conninfo)` — same contract
- `build_default_branch_store(*, project_root) -> SqliteDefaultBranchStore | PostgresDefaultBranchStore`
- `RepositoryIngestionService.__init__(..., default_branch_reader=None, default_branch_writer=None)`
- `RepoSummary.default_branch: str | None = None` (`api/schemas.py`)
- Frontend: `_linkifyPaths(html, canonicalUrl, defaultBranch)`,
  `isLinkablePath(text)`, `_pathToGithubUrl(path, canonicalUrl, branch)`
  (`static/app.js`)

## 10. Evidence requirements

Not applicable in the CODEX.md sense — no LLM-generated interpretive claim is
involved. The default branch is a raw git fact read directly from the local
clone; linked paths are the LLM's own backtick-wrapped text, rendered as-is
(not verified against the repository's actual file tree, same posture as
SHA-linking).

## 11. Failure modes

| Failure | Behavior |
|---|---|
| `HEAD` is detached in the local clone | Reader returns `None`; nothing persisted (AC-02). |
| `HEAD`'s resolved ref name fails the safe-charset check | Reader returns `None`; nothing persisted (AC-03). |
| `git.Repo(cache_path)` raises (corrupt/missing clone) | Reader returns `None` (caught internally, never propagates). |
| `clone_or_fetch` fails | Reader is never called (AC-04). |
| Repository has no stored default branch | API returns `default_branch: None`; frontend renders no path links, only plain code spans (AC-05, AC-07). |
| `canonical_url` is not a GitHub URL | Frontend never attempts path linking (AC-07). |
| A code span's text fails the path-plausibility heuristic | Left as a plain, unlinked `<code>` span. |
| A code span is inside a fenced `<pre><code>` block | Never considered for linking, regardless of content (AC-06). |
| A path segment happens to be entirely hex digits and 7-40 characters long (e.g. `src/deadbeef.py`) | `_linkifyCommitShas` runs first and operates on raw HTML text without regard to `<code>` boundaries, so it turns that substring into a `commit/<hex>` link before path-linking sees the span; the span then fails path-linking's content-purity check (`[^<]*`) and is left as-is. Accepted, narrow limitation — no corruption (verified: no nested/malformed anchors), just a missed blob link for the rare path whose name is a pure hex string. Not fixed in this batch: fixing it would require teaching `_linkifyCommitShas` about `<code>` boundaries, which is out of scope (non-goal: no change to existing SHA-linking behavior). |

## 12. Security considerations

- **Untrusted branch names**: a repository's default branch name is read
  directly from local git ref data. Even though the git porcelain refuses to
  *create* refs with unsafe characters, `HEAD`'s target is read as raw text
  and is treated as untrusted per CODEX.md — validated against a fixed safe
  charset before it is ever persisted or exposed via the API (AC-03).
- **Untrusted narrative/path text**: the text inside backtick-wrapped code
  spans originates from LLM-generated narratives or chat replies, which are
  themselves grounded in repository content (CODEX.md: treat repository text
  as untrusted input). `isLinkablePath` re-validates the same safe charset
  client-side before building any URL — a span is either fully safe to
  interpolate into a URL path or it is left alone as plain text; there is no
  partial/best-effort escaping path.
- **No native `title=` tooltips holding unescaped content**: linked path text
  is escaped via the existing `esc()` helper before being placed back into
  the rendered HTML, exactly like `_linkifyCommitShas` already does for SHA
  text.
- **Ordering is a security property, not just a rendering nicety**: running
  `_linkifyPaths` before `_linkifyCommitShas` would let the SHA-linkifier's
  bare-hex-token regex match visible link text nested inside an already-built
  `<a href="...blob...">` (e.g. an 8-hex-char substring inside a path like
  `src/deadbeef.py`), producing a nested `<a>` inside another `<a>` —
  malformed HTML with unpredictable click behavior. Running SHA-linking first
  avoids this: any code span that already contains a SHA-produced `<a>` tag
  fails path-linking's `[^<]*` content-purity check and is safely skipped,
  never re-processed (AC-08). The accepted tradeoff of this ordering — a path
  whose name is itself a pure 7-40-char hex string loses its blob/tree link in
  favor of an (also harmless) commit link — is documented in Failure modes.
- **Fenced code blocks are never linkified**: `(?<!<pre>)<code>` guards
  against rewriting arbitrary command/config text inside fenced blocks, which
  could otherwise be misread as safe paths.
- **URL-encoding**: each path segment is passed through `encodeURIComponent`
  before being joined back with `/`. Given the safe charset already excludes
  every character `encodeURIComponent` would change, this is a no-op today
  and a forward-compatible safety net if the charset is ever loosened.

## 13. Privacy considerations

Default branch names and file/folder paths are already-public repository
metadata (visible to anyone browsing the repository on GitHub). No new
personal data is collected, logged, or transmitted.

## 14. Observability

- No new logging beyond what `_ingest_bg`'s existing broad `except Exception`
  already provides — `GitPythonDefaultBranchReader` never raises, so there is
  nothing distinct to log on the happy/degraded path.

## 15. Tests required

### Automated tests (pytest, TDD — failing first)

- `tests/unit/test_default_branch_reader.py` (new): resolves the branch name
  from a real local bare-clone fixture (mirrors
  `test_git_commit_extractor.py`'s `bare_fixture_repo` pattern); detached HEAD
  (simulated by rewriting the bare clone's `HEAD` file to a raw SHA) returns
  `None`; unsafe branch name (simulated by rewriting `HEAD` to
  `ref: refs/heads/weird;name`) returns `None`; a non-existent/corrupt clone
  path returns `None` without raising.
- `tests/unit/test_repository_ingestion_service.py` (extended): default
  branch reader/writer called only after a successful `clone_or_fetch`; writer
  invoked with the resolved branch name keyed by `repository_id`; writer never
  called when the reader returns `None`; reader/writer never called on a
  `GitGatewayError`; behavior unchanged (no error) when neither port is
  wired.
- `tests/unit/test_default_branch_store_sqlite.py` (new): insert + read
  roundtrip, upsert overwrites, get on unknown repository_id returns `None`,
  distinct repositories are independent, `initialize()` is idempotent —
  mirroring `test_repo_metadata_store_sqlite.py`'s structure.
- `tests/unit/test_postgres_adapters.py` (extended): `PostgresDefaultBranchStore`
  roundtrip + upsert, gated by the existing
  `DATABASE_URL`-must-start-with-`postgresql` skip.
- `tests/unit/test_api_repos.py` (extended): `GET /api/repos` includes
  `default_branch`; populated when stored; `None` when absent.
- `tests/unit/test_api_delete.py` (extended): deleting a repository removes
  its default-branch row too.

### Manual/e2e verification (Playwright, run by the orchestrator)

1. Ingest a public GitHub repository. Confirm its case study narrative renders
   a backtick-wrapped file path (e.g. `` `src/x.py` ``) as a link to
   `.../blob/<default_branch>/src/x.py`, and a backtick-wrapped folder
   reference (e.g. `` `tests/` ``) as a link to
   `.../tree/<default_branch>/tests/`.
2. Confirm a plain-word code span like `` `True` `` in the same narrative is
   NOT turned into a link.
3. Confirm fenced code blocks in the narrative render unchanged (no accidental
   linkification of code/config content).
4. Confirm commit-SHA links elsewhere in the same narrative still work
   correctly alongside the new path links (no corruption from running both
   linkifiers on the same HTML).

### Evaluation required

Not applicable — no LLM call is involved in this feature.

## 16. Documentation impact

- `docs/progress/ingestion/batch-96-file-folder-path-linking.md` records this
  batch's work (filed under `ingestion/` since the primary new capability —
  default-branch capture — lives in the ingestion pipeline; the frontend
  linkification is the consuming feature).
- `docs/progress/README.md` gets a new entry.

## 17. ADR impact

None. This is an additive port + store + API field + frontend rendering
feature within the existing hexagonal layering — no new architectural
boundary is introduced. Placing default-branch capture inside
`RepositoryIngestionService` (rather than the route-level `_ingest_bg`, where
spec 019's GitHub metadata fetch lives) is documented here as a locked
decision, not an ADR, because it does not change any existing boundary — it
uses the exact same optional-port pattern the service already has for commit
extraction.

## 18. Open questions

- **Should default branch be refreshed if a repository's actual default
  branch changes on GitHub after ingestion?** Assumption made: no — a
  re-ingestion (fetch, not re-clone) does not update the local clone's `HEAD`
  symref in the common case, so this could go briefly stale. Out of scope;
  the existing "fetch-once" precedent from spec 019 applies here too. A
  future batch could force-update `HEAD` on re-fetch if this proves painful.
- **Should the 8-extension list be configurable?** Assumption made: no, fixed
  list is enough for a first slice; matches spec 019's precedent of a fixed,
  non-configurable list (language palette) shipped without a
  configuration surface.

## 19. Out of scope

- Free-text (non-backtick) path detection.
- Path-existence verification against the repository's actual file tree.
- A default-branch refresh/backfill endpoint or scheduled job.
- Any change to spec 019's `RepoMetadata`/`repo_metadata` table.
- A JS unit-test framework (same investigated-and-confirmed absence as specs
  016/017/018/019).
