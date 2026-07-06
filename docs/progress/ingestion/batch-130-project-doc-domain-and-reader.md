## Batch 130 — Project-doc domain model and GitPython README/CHANGELOG reader (spec 025, slice 1)

### Goal

Lay the first slice of spec 025 (README/CHANGELOG context for case study
narratives): the `ProjectDocContent` domain shape, the `ProjectDocReader` /
`ProjectDocWriter` ports, and `GitPythonProjectDocReader` — a reader that
captures a repository's root-level README/CHANGELOG directly from the bare
git clone already used for commit mining. No stores, no service wiring, no
narrative-prompt integration land here; those follow in later batches
(131-133), matching the spec's locked TDD order (domain → reader → stores →
service wiring → narrative integration) and mirroring how spec 020's
default-branch capture and spec 023's embedding foundation were built
bottom-up.

### Why

Spec 025 is spec-only; nothing was implemented when it was authored (batch
129). `NarrativeService` currently infers a project's purpose only from
commit content — a README/CHANGELOG excerpt costs nothing extra to obtain
(the bare clone already exists) and grounds the narrative's opening more
reliably. Building this bottom-up keeps each slice independently green and
reviewable.

### What was added

**`domain/project_docs.py`** (new)
- `ProjectDocContent` — frozen dataclass (not Pydantic — an internal,
  backend-agnostic persistence shape, not an LLM-output-validation boundary,
  same rationale as `EmbeddedChunk`). Fields: `repository_id`, `readme_text:
  str | None`, `readme_truncated: bool`, `changelog_text: str | None`,
  `changelog_truncated: bool`, `captured_at: datetime`. One record per
  repository (not one row per source), since there are always exactly two
  possible sources.

**`application/ports.py`** — two new Protocols, placed next to
`DefaultBranchReader`/`DefaultBranchWriter` for logical grouping:
- `ProjectDocReader.get_project_docs(repository_id: str) -> ProjectDocContent | None`
- `ProjectDocWriter.save_project_docs(content: ProjectDocContent) -> None`

**`infrastructure/project_docs.py`** (new file, not added to `commits.py`)
- `GitPythonProjectDocReader(cache_path)` — opens the bare clone via
  GitPython (mirrors `GitPythonDefaultBranchReader`'s exact approach),
  reads `HEAD`'s commit tree, matches root-level blobs only (no `docs/`
  folder, no nested paths — locked decision) against a case-insensitive
  name list (`readme.md`, `readme.rst`, `readme.markdown`, `readme.txt`,
  `readme`; same pattern for `changelog`), decodes as UTF-8, truncates to
  `PROJECT_DOC_MAX_CHARS` (env-var-backed constant, default 2000, batch-74
  convention). Skips a file entirely on `UnicodeDecodeError` rather than
  producing garbled `errors="replace"` output (spec's proposed default,
  now locked at implementation time). Returns `None` when neither file is
  found — the signal the caller (batch 132) uses to skip persistence
  entirely. Never raises: missing/corrupt clone path, detached HEAD, and
  any GitPython exception all degrade to `None`, matching
  `GitPythonDefaultBranchReader`'s "never raises" contract exactly.
- Placed in its own dedicated module rather than `infrastructure/commits.py`:
  this reader does meaningfully more work (tree traversal, case-insensitive
  matching across two name lists, decoding, truncation) than the one-line
  HEAD-ref read `GitPythonDefaultBranchReader` performs, and `commits.py` is
  already a sizable file covering commit extraction and default-branch
  capture.

### Tests added

- `tests/unit/test_project_docs_domain.py` (4 tests): `ProjectDocContent`
  constructs with both fields present, README-only, CHANGELOG-only, and with
  truncation flags set.
- `tests/unit/test_git_project_doc_reader.py` (11 tests): reads `README.md`
  from a real bare-clone fixture; reads `CHANGELOG.md` independently (no
  README present); both present in the same `ProjectDocContent`;
  case-insensitive name/extension matching (`Readme.md`, `README.rst`,
  `readme.markdown`); missing file (neither present) → `None`; oversized
  file → truncated with `readme_truncated=True`; same-shape file under
  budget → `readme_truncated=False`; non-UTF8 blob content → that file
  skipped, not raised (the other file, if present, still captured); missing
  clone path → `None` without raising.

Full suite: **969 passed, 24 skipped** (unchanged skip count — the 24 skips
are the pre-existing Postgres-gated tests; none of this batch's tests are
skipped).

### Gotchas

- Windows' `Path.write_text()` silently translates `"\n"` to `os.linesep`
  (`"\r\n"`) unless `newline=""` is passed — the reader's own bare-clone test
  fixture hit this (`README.md` content compared with LF-only expectations
  failed until the fixture writer used `newline=""`). Not a reader bug: the
  reader decodes exactly whatever bytes GitPython hands back from the blob;
  the mismatch was purely in how the test fixture wrote the *source* file
  before committing it.
- `git.Repo.head.commit.tree` (used here) does not raise for a detached
  HEAD, unlike `git.Repo.head.reference` (used by
  `GitPythonDefaultBranchReader`) — this reader doesn't care about branch
  names, only the tree at whatever commit `HEAD` currently points to, so no
  detached-HEAD special-casing was needed here.
- `GitPythonProjectDocReader`'s own method is named `read_project_docs`
  (mirroring `GitPythonDefaultBranchReader`'s `read_default_branch` naming
  for a git-clone-reading class), while the `ProjectDocReader` Protocol
  method is `get_project_docs` (mirroring the "get_" prefix most other
  reader ports in `ports.py` use). The two names are deliberately distinct
  in this slice: `GitPythonProjectDocReader` is not wired as a
  `ProjectDocReader` yet (that decision — capture-time git read vs.
  persisted-store read — belongs to batch 132's service wiring). Flagging
  this now so the next batch resolves it explicitly rather than assuming
  structural conformance.
- mypy flagged `blob.data_stream.read().decode("utf-8")` as `Returning Any`
  (GitPython's stream read is typed loosely) — fixed with an explicit
  `bytes` annotation on the intermediate variable rather than a blanket
  `# type: ignore`.

### Commits

- `feat: add project-doc domain model and GitPython README/CHANGELOG reader (spec 025)`
