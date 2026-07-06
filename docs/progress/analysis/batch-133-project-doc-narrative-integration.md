## Batch 133 — Add project documentation context to case-study narrative prompt (spec 025, slice 4)

### Goal

Wire the captured `ProjectDocContent` (domain: batch 130; reader: batch 130; stores: batch
131; ingest-time capture: batch 132) into `NarrativeService` so both the full and incremental
narrative-generation prompts can include the project's own README/CHANGELOG excerpt as
background/framing context. This is the final application-layer slice of spec 025; unlike
spec 022's equivalent narrative-wiring batch (110), this batch **also** wires the reader into
`composition.py`'s production `build_narrative_service` factory in the same batch, since the
underlying store (`build_project_doc_store`) already existed from batch 132 — no reason to
leave it stranded for a separate follow-up the way discussion evidence briefly was.

### What was added

**`application/narrative_service.py`**
- `NarrativeService.__init__` gained an optional, keyword-only `project_doc_reader:
  ProjectDocReader | None = None`, following the exact pattern of `discussion_reader`. `None`
  is fully backward compatible — no project-doc content is read or rendered.
- `_generate_full` and `_generate_incremental` both read
  `self._project_doc_reader.get_project_docs(repository_id)` (or `None` when no reader is
  configured — note this defaults to `None`, not `[]`, matching `ProjectDocReader`'s own
  single-object return type, unlike `discussion_evidence`'s list default) and pass it into the
  corresponding `_build_*_user_message` method.
- `_build_user_message` and `_build_incremental_user_message` each gained a
  `project_docs: ProjectDocContent | None = None` parameter. A new module-level helper,
  `_append_project_doc_block(lines, project_docs)`, appends a `## Project Documentation`
  block immediately after the Discussion Evidence block, rendering `### README`/`###
  CHANGELOG` sub-sections only for whichever file was actually captured, and omitting the
  whole block when `project_docs is None` or both text fields are `None`.
- **Deliberately no citation instruction, no `evidence_ref`, no per-item source suffix** —
  unlike Discussion Evidence's `(source: {url})` pattern. The block instead carries an
  explicit framing sentence ("treat as the maintainers' own stated description, not an
  independently-verified fact"), since spec 025 locked "truncate only, no summarization, no
  new citation type" — this content has no evidence reference to point to by design, and the
  framing sentence is what prevents the model from accidentally citing it with the same
  evidentiary weight as a commit- or Discussion-sourced claim (ADR 004).

**`composition.py`**
- `build_narrative_service`'s both backend branches (SQLite and PostgreSQL) now also pass
  `project_doc_reader=build_project_doc_store(project_root=project_root)` to the
  `NarrativeService(...)` constructor, alongside the existing `discussion_reader=...` line —
  so this feature is live in production narrative generation immediately, not stranded behind
  a later wiring batch.

**`docs/prompt-contracts/narrative-generation.md`**
- New "Project documentation block (spec 025, Batch 133)" section, mirroring the existing
  Discussion Evidence section's depth/format, explicitly documenting the no-citation framing
  rationale.

### Tests added

`tests/unit/test_narrative_service.py` (+12 tests, all green):
- `_build_user_message` / `_build_incremental_user_message`: block present with correct text
  when `project_docs` given; block entirely absent when `project_docs=None`.
- README-only, CHANGELOG-only, and both-present rendering (correct sub-section shown/hidden
  in each case).
- Framing-language assertion: the block contains "project documentation", "own", and "not an
  independently-verified fact" (guards against the framing sentence being dropped/reworded
  away in a future edit without a test failure).
- No-citation assertion: the project-doc section of the message never contains `(source:`
  (guards against someone copy-pasting the Discussion Evidence citation pattern onto this
  block by habit).
- End-to-end via `NarrativeService.generate(...)`: a service constructed with a stub
  `project_doc_reader` produces a user message (captured via `FakeLLMClient`) containing the
  block; a service constructed without one (the default) omits it; a service whose reader
  returns `None` also omits it.

Full suite: **992 passed, 27 skipped** (up from 980 passed / 27 skipped after batch 132 — the
skip count is unaffected, Postgres-gated tests unchanged; +12 new project-doc tests. No
regressions).

### Gotchas

- This batch picked up mid-flight after a prior session was interrupted by a hit session
  limit partway through. The interrupted work had already written the full RED test suite
  (14 tests) and the standalone `_append_project_doc_block` helper function, but had not yet
  wired the constructor parameter, the two `_generate_*` fetch sites, the two
  `_build_*_user_message` signatures, or the two append-call sites. Verified via `git status`/
  `git diff` before resuming — the partial state was safe (an unused helper function, no
  broken call sites) rather than inconsistent, so the remaining wiring was completed directly
  rather than re-running the whole batch from scratch.
- `project_docs` defaults to `None` in both `_build_user_message` and
  `_build_incremental_user_message` specifically so no existing caller (there are none that
  pass it positionally in the pre-batch-133 test suite) breaks; the already-written tests call
  `_build_user_message` positionally with 4 args (`items, report, [], docs`), which works
  because `project_docs` is declared right after `discussion_evidence` with a default,
  preserving positional-call compatibility.
- `build_narrative_service` already wired `discussion_reader` for both backends (confirmed by
  reading the function before editing) — this made it a one-line addition per branch rather
  than a decision to defer, unlike spec 022's own batch 110, which explicitly left composition
  wiring for a later slice because the discussion-evidence store didn't yet have a stable
  factory function at that point in the build sequence.

### Commits

- `feat: add project documentation context to case study narrative prompt (spec 025)`
