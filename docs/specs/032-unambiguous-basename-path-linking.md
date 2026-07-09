# Spec 032: Unambiguous Basename Path Linking

**Status:** Implemented
**Spec number:** 032
**Author:** Rafael Castaño
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: Security Agent, Quality Agent
Created: 2026-07-09
Updated: 2026-07-09

## 1. Summary

The case-study narrative (and the Ask-tab answers) link backtick-wrapped file/folder
paths to GitHub, but only when the span is a **full repository-relative path**
containing a `/` (`isLinkablePath`, `static/app.js:2064` — `return text.includes('/')`).
A **bare basename** span such as `` `ports.py` ``, `` `app.css` ``, or `` `issues.go` ``
— no slash — is rejected and rendered as plain `<code>`, even though the file plainly
exists in the repository.

This is a real, observed inconsistency. The narrative LLM (per the
`narrative_service.py` prompt, lines 96–99) is asked to write full paths, and it does
so for the **first** mention of a file, which links — but it naturally shortens
**repeated** mentions to the bare basename, which does not. Direct evidence from a
stored case study (git_it's own narrative, `repo-5d393bf9afc7`):

- `` `src/git_it/repository_ingestion/application/ports.py` `` (full path) → **links**;
- two lines later, *"A 'port' (in `` `ports.py` ``)"* (bare basename) → **does not link**.

Since spec 029, the frontend already holds the repository's **verified file-path set**
(`filePathSet`, from `GET /api/repos/{id}/file-paths`). That set makes it safe to
resolve a bare basename to its full path **when the basename is unambiguous** — exactly
one tree member has that basename. This spec adds that resolution: a bare-basename span
links to the real file **iff** it maps to a single verified tree member; ambiguous or
unknown basenames stay plain `<code>`, so the spec-029 guarantee ("never a broken link;
only tree-verified paths are linked") is preserved.

## 2. Problem

Bare-basename file references in generated narratives do not link, so the same file is
clickable in one sentence and plain text in the next. The `/`-required rule
(`isLinkablePath`) was correct **before** spec 029 — without the tree, a bare basename
could not be located and `/blob/<branch>/ports.py` would 404 for a nested file. With the
verified tree now available, a unique basename can be located exactly, so the old
limitation no longer needs to hold for unambiguous cases.

## 3. Goals

- Link a backtick-wrapped **bare basename** (no `/`) to its file on GitHub **iff** it
  resolves to exactly **one** member of the verified `filePathSet` (by basename).
- Keep the resolution **confirmatory-only** (spec 029 spirit): an ambiguous basename
  (two or more tree members share it) or an unknown basename (zero members) stays plain
  `<code>` — never link a guess, never a broken link.
- Restrict bare-basename resolution to **file** references that carry an **extension**
  (a `.` in the basename), so tool/function names (`manage_mcp`) and bare folder words
  (`interfaces`) are not mis-linked.
- Leave the existing spec-029 **slashed-path** behavior byte-identical (exact member →
  file/blob; directory prefix → folder/tree; unverified → plain).
- Apply uniformly to the **case-study narrative** and the **Ask-tab answers** (both flow
  through `_linkifyPaths`), with no backend change (reuse spec 029's `/file-paths`).

## 4. Non-goals

- **No free-text (non-backtick) path detection.** Only `<code>` spans are ever
  considered — spec 020's locked decision is unchanged.
- **No LLM prompt change.** The user chose "Option B alone": the prompt already asks for
  full paths; this feature catches the bare basenames the LLM writes for repeat mentions.
  Forcing full paths on every repeat mention would harm narrative readability.
- **No bare-folder resolution.** Only extensioned file basenames resolve; a bare folder
  word (`tests`, `interfaces`) is too ambiguous and stays plain. Folder links still
  require the explicit `path/` form (spec 029).
- **No fuzzy / nearest-match resolution.** Exact basename equality only.
- **No new endpoint, store, or migration.** The verified file-path set already exists
  (spec 029).

## 5. Users

- A learner reading a case study or Ask answer who wants every mention of a real file —
  first or repeated, full path or shorthand — to open that file on GitHub.

## 6. User stories

- As a learner, when the narrative shortens a file to its basename (`` `ports.py` ``),
  the shorthand still links to the real file, just like its first full-path mention did.
- As a learner, when a basename is ambiguous (`` `__init__.py` ``) or names a file that
  no longer exists (`` `sqlite.py` `` after a package split), it stays plain text rather
  than sending me to a wrong or broken page.

## 7. Acceptance criteria

- **AC-01** Given a backtick span that is a bare basename (no `/`) containing a `.`, and
  exactly **one** member of `filePathSet` has that basename, then the span is linked to
  that member's `.../blob/<branch>/<full-path>` URL; the **visible text** is the basename
  and the **`title`** is the full resolved path.
- **AC-02** Given a bare basename that is the basename of **two or more** members of
  `filePathSet` (ambiguous), then the span stays plain `<code>` (no link).
- **AC-03** Given a bare basename that matches **zero** members of `filePathSet`
  (unknown, or a removed file), then the span stays plain `<code>`.
- **AC-04** Given a bare token **without** a `.` in it (e.g. `manage_mcp`, `interfaces`),
  then bare-basename resolution is **not** attempted and the span stays plain `<code>`.
- **AC-05** Given a slashed path span, the spec-029 behavior is unchanged: exact member →
  file/blob link; directory prefix of a member → folder/tree link; unverified → plain.
- **AC-06** The **raw span text** (untrusted LLM output) is used **only** as a lookup key
  against the verified set; the linked full path, the visible text, and the `title` are
  all derived from the **verified tree member**. The resolved path is re-validated with
  `_isSafePathLikeString` before URL interpolation, escaped via `esc()` for text/`title`,
  and `encodeURIComponent`-ed per segment for the URL (defense in depth, spec 029 §12).
- **AC-07** Given an empty/absent `filePathSet`, or an unusable `defaultBranch`/
  `canonicalUrl`, then `_linkifyPaths` returns the html unchanged (no slashed **or**
  bare-basename linking) — unchanged from spec 029 AC-07.
- **AC-08** The basename → full-path index is computed **once per `_linkifyPaths`
  invocation** (O(N) over the set once), not once per span (no O(N·spans) blowup).
- **AC-09** Bare-basename linking applies to **both** the case-study narrative render path
  and the Ask-tab answer render path (both call `_linkifyPaths` via the same helper).

## 8. Domain concepts

- **Bare basename**: a safe path-like span with no `/` and at least one `.` (an
  extensioned filename), e.g. `ports.py`, `app.css`, `issues.go`.
- **Unambiguous resolution**: a basename that is the basename of exactly one tree member;
  it resolves to that member's full path. Two-or-more matches = **ambiguous** (no link);
  zero matches = **unknown** (no link).
- **Basename index**: a `Map<basename, fullPath | AMBIGUOUS>` built once from
  `filePathSet`, keyed only by basenames containing a `.`. The ambiguity sentinel marks a
  basename seen on more than one member.

## 9. Inputs and outputs

- **New pure helper** `_basenameIndex(filePathSet) -> Map<string, string | null>`:
  iterates the set once; for each member whose basename contains `.`, records
  `basename → fullPath`, or `basename → null` (ambiguity sentinel) once a second member
  shares that basename.
- **New pure helper** `_resolveUniqueBasename(text, basenameIndex) -> string | null`:
  returns the full path when `text` has no `/`, is a key of the index, and the mapped
  value is a non-null string; otherwise `null`.
- **`_linkifyPaths` change** (`static/app.js`): build the basename index once before the
  `replace`. In the callback, after the existing `_isSafePathLikeString(text)` guard:
  if `isLinkablePath(text)` (slashed) → spec-029 branch (`_verifyTreePath`); else →
  bare-basename branch (`_resolveUniqueBasename`, `kind = 'file'`). Both branches then
  share one anchor build using the **resolved full path** for href/`title` and its
  basename for the visible text.
- **No API/store/migration change.** `filePathSet` is the spec-029 verified set.

## 10. Evidence requirements

- Not an LLM/interpretation claim. A link is factual: the basename resolves to exactly
  one real, verified tree member or it does not link. No confidence/limitations fields.

## 11. Failure modes

- **Ambiguous basename** → no link (AC-02). Safety over coverage (user-confirmed).
- **Unknown / removed-file basename** → no link (AC-03).
- **Empty/absent tree, unusable branch/URL** → html unchanged (AC-07).
- **Hostile span text** (untrusted) → used only as a Map key; if it is not an exact key of
  the verified index it does not link, and the interpolated path/text always come from the
  verified tree, never from the raw span (AC-06).

## 12. Security considerations

- Repository content — file paths, and the narrative's own file references — is untrusted
  input (CODEX §7). The raw backtick span text is used **only** as a lookup key; it is
  never interpolated into markup or a URL. The href, visible text, and `title` derive from
  the server-verified, charset-filtered `filePathSet` (spec 029), are re-validated with
  `_isSafePathLikeString`, escaped via `esc()`, and `encodeURIComponent`-ed per URL
  segment. A hostile or ambiguous span cannot produce a link to an off-tree path or inject
  markup. No new external surface.

## 13. Privacy considerations

- None. Paths are already public in the analyzed public repository and already served by
  spec 029's `/file-paths`. No new data collected or exposed.

## 14. Observability

- None required (pure client-side rendering). No new logs.

## 15. Tests required

Following the spec-029 convention (`tests/unit/test_api_static.py`): source-string
assertions on the served `app.js`, extracting the relevant function bodies and asserting
the governing constructs. New/updated tests:

- `_basenameIndex` exists, iterates the set once, keys only basenames containing `.`, and
  records the ambiguity sentinel on a second match (AC-01/AC-02/AC-04/AC-08).
- `_resolveUniqueBasename` returns the full path only for a no-slash key mapped to a
  non-null value; null otherwise (AC-01/AC-02/AC-03).
- `_linkifyPaths` builds the index once (outside `replace`) and branches: slashed →
  `_verifyTreePath`; bare → `_resolveUniqueBasename` with `kind = 'file'`; the resolved
  full path (not the raw span) feeds href/`title`, the basename feeds visible text
  (AC-05/AC-06/AC-08).
- The spec-029 anchor-escaping assertions are updated to the new variable that carries the
  resolved path, preserving `esc()`/`encodeURIComponent`/basename-visible behavior for the
  slashed branch (byte-identical rendering, AC-05/AC-06).
- The `isLinkablePath` slash rule stays intact (still `text.includes('/')`) — the
  bare-basename path lives in `_linkifyPaths`, not in `isLinkablePath` (AC-05).

## 16. Evaluation required

- None (no LLM prompt or output change — the LLM's text is unchanged; only rendering
  resolves more of it).

## 17. Documentation impact

- `docs/architecture.md` roadmap: add spec 032 (Implemented on completion).
- `docs/progress/{api}/batch-{N}-unambiguous-basename-path-linking.md` + README index
  entry.
- Update the stale intent comment on the spec-156/029 `isLinkablePath` test to note that
  bare-basename linking is now handled (safely, via tree uniqueness) in `_linkifyPaths`.

## 18. ADR impact

- None. No new architectural pattern; extends the existing spec-020/029 client-side
  linkifier within its established seam.

## 19. Open questions

- None blocking. The extension (`.`) requirement for bare basenames is an explicit
  safety/precision decision (§3, §7 AC-04): it covers every observed real case
  (`.py`/`.css`/`.js`/`.go`/`.html`/`.md`) while excluding tool names and bare folders;
  the rare extensionless real file (`Makefile`) simply keeps requiring its full-path form.
