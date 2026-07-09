## Batch 161 — Unambiguous basename path linking (spec 032)

### Goal

Fix an observed inconsistency in case-study and Ask-tab rendering: some file references
link to GitHub and others do not. Root cause (evidence: git_it's own stored narrative,
`repo-5d393bf9afc7`) — the narrative LLM writes a file's **first** mention as a full
repository-relative path (`` `src/git_it/repository_ingestion/application/ports.py` ``),
which links, but shortens **repeated** mentions to the bare basename (`` `ports.py` ``),
which the linkifier rejected. The rejecting rule is `isLinkablePath` (`static/app.js`),
whose `return text.includes('/')` gate drops any span without a slash. That gate was
correct **before** spec 029 (without the file tree, a bare basename could not be located
and `/blob/<branch>/ports.py` would 404 for a nested file), but spec 029 now gives the
frontend the repository's **verified file-path set**, so a unique basename can be resolved
to its real full path safely.

### What was added

**`static/app.js`**
- `_basenameIndex(filePathSet)`: builds a `basename -> full path` `Map` **once per
  `_linkifyPaths` call** (not per span). Only basenames containing a `.` (extensioned
  files) are indexed, so tool/function names (`manage_mcp`) and bare folder words
  (`interfaces`) are never basename-resolved. A basename shared by two-or-more members
  maps to `null` — the ambiguity sentinel.
- `_resolveUniqueBasename(text, basenameIndex)`: returns the full path only for a
  no-slash span whose basename maps to a single (non-null) member; returns `null` for a
  slashed span (handled by the spec-029 branch), an unknown basename, or an ambiguous one.
- `_linkifyPaths` now branches inside the `<code>`-span replace: a **slashed** span keeps
  the spec-029 path (`_verifyTreePath` → file/blob or folder/tree); a **bare basename**
  span uses `_resolveUniqueBasename` with `kind = 'file'`. Both branches feed the
  **resolved full path** (`linkPath`) — never the raw span — into the URL, `title`, and
  (via its basename) the visible text.

No backend, API, store, migration, or LLM-prompt change: the `/file-paths` verified set
already exists (spec 029), and the narrative prompt already asks for full paths — this
feature only makes rendering resolve the bare basenames the LLM writes for repeat mentions.
The user chose "Option B alone" (resolution only, no prompt change): forcing full paths on
every repeat mention would harm narrative readability.

### Behavior (spec 032 acceptance criteria)

- **AC-01** `` `ports.py` `` with exactly one tree member ending in `/ports.py` →
  links to that member's `blob` URL; visible text `ports.py`, `title` the full path.
- **AC-02** `` `__init__.py` `` (many tree members) → plain `<code>`.
- **AC-03** `` `sqlite.py` `` (removed after a package split; not in the tree) → plain.
- **AC-04** `` `manage_mcp` `` / `` `interfaces` `` (no extension) → never resolved, plain.
- **AC-05** Slashed paths keep the spec-029 behavior byte-identical.
- **AC-06** The untrusted raw span is used only as a `Map` key; href/text/`title` derive
  from the verified tree, are re-validated with `_isSafePathLikeString`, escaped via
  `esc()`, and `encodeURIComponent`-ed per URL segment. A hostile span stays plain.
- **AC-07** Empty/absent set or unusable branch/URL → html unchanged.
- **AC-08** The basename index is built once per invocation.
- **AC-09** Applies to both the case-study narrative and Ask-tab answers (shared
  `_linkifyPaths`).

### Tests added

`tests/unit/test_api_static.py` (source-string assertions on served `app.js`, the
spec-029 convention):
- `test_static_app_js_basename_index_keys_only_extensioned_and_marks_ambiguous` — index
  built from the last path segment, keyed only on extensioned basenames, ambiguity
  sentinel on a second match (AC-01/AC-02/AC-04/AC-08).
- `test_static_app_js_resolve_unique_basename_only_for_no_slash_unique` — no-slash guard;
  only a non-null (unique) mapping resolves (AC-01/AC-02/AC-03).
- `test_static_app_js_linkify_paths_resolves_bare_basename_as_file` — index built once
  before `replace`; bare branch resolves to a `file` link; the resolved `linkPath` (not
  the raw span) is charset-revalidated and fed to the URL (AC-01/AC-05/AC-06/AC-08).
- Updated the spec-029 anchor/`_verifyTreePath` assertions to the new `linkPath` variable
  (slashed-path rendering is byte-identical) and refreshed the stale intent comment on
  `test_static_app_js_linkable_path_requires_a_slash` (bare-basename handling now lives in
  `_linkifyPaths`, not in `isLinkablePath`).

Behavior was additionally verified out-of-band by executing the extracted helpers in Node
against a fixture tree (unique → link, ambiguous/unknown/no-extension/hostile → plain).

### Gotchas

- The **extension (`.`) requirement** for bare basenames is a deliberate safety/precision
  choice: it covers every observed real case (`.py`/`.css`/`.js`/`.go`/`.html`/`.md`) while
  excluding tool names and bare folder words. A rare extensionless real file (`Makefile`)
  simply keeps requiring its full-path form.
- `isLinkablePath` is intentionally **unchanged** (still `text.includes('/')`) — it gates
  only the slashed branch; the bare-basename path lives in `_linkifyPaths`.

### Commits

- `feat: unambiguous basename path linking in case studies and chat (spec 032)`
