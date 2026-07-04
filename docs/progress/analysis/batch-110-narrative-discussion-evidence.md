## Batch 110 — Feed discussion evidence into the case-study narrative prompt (spec 022, slice 4)

### Goal

Wire the schema-validated `DiscussionEvidence` items (foundation: batch 107; fetcher:
batch 108; summarizer: batch 109) into `NarrativeService` so both the full and incremental
narrative-generation prompts can cite discussion-derived design rationale and pain points
alongside commit evidence. This is slice 4 of spec 022's build order (fetcher → summarizer →
narrative → wiring); ingest-time wiring (calling the fetcher/summarizer and persisting
evidence during a real ingestion run) is a later batch.

### Why

`DiscussionEvidenceReader` (`get_discussion_evidence(repository_id) -> list[DiscussionEvidence]`)
and the SQLite/PostgreSQL stores already existed (batch 107) but had no reader in the
narrative path — discussion evidence was persisted but never reached the LLM prompt. This
batch closes that gap without touching ingestion or summarization.

### What was added

**`application/narrative_service.py`**
- `NarrativeService.__init__` gained an optional, keyword-only `discussion_reader:
  DiscussionEvidenceReader | None = None`, following the exact pattern of the existing
  optional `case_study_store`/`synopsis_store` dependencies. `None` is fully backward
  compatible — no discussion evidence is read or rendered.
- `_generate_full` and `_generate_incremental` both read
  `self._discussion_reader.get_discussion_evidence(repository_id)` (or `[]` when no reader
  is configured) and pass the list into the corresponding `_build_*_user_message` method.
- `_build_user_message` and `_build_incremental_user_message` each gained a
  `discussion_evidence: list[DiscussionEvidence]` parameter. A new module-level helper,
  `_append_discussion_evidence_block(lines, discussion_evidence)`, appends a
  `## Discussion Evidence` block **immediately before** the closing `[/REPOSITORY DATA]`
  tag — one line per item, shaped exactly as
  `- [{claim_type}] {summary}  (source: {discussion_url})`. When the list is empty, the
  function is a no-op: the envelope is byte-identical to pre-batch-110 output for
  repositories with no discussion evidence.
- Both `_BASE_PROMPT` and `_BASE_INCREMENTAL_PROMPT` gained one literal sentence (no new
  `.format()` placeholder) next to the existing "every major claim must cite" sentence:
  any claim derived from the Discussion Evidence block must repeat the exact `source:` URL
  given for that item, and the model must not state a discussion-derived claim for which no
  source URL was provided.
- The block is built only from `DiscussionEvidence` fields (`claim_type`, `summary`,
  `discussion_url`) — there is no `Discussion` (raw, ephemeral) object in scope in this
  layer at all, so raw discussion body/title text cannot leak into the prompt by
  construction.

### Tests added

`tests/unit/test_narrative_service.py` (+8 tests, all green):
- `_build_user_message` / `_build_incremental_user_message` each get one test asserting the
  `## Discussion Evidence` block renders with `[claim_type] summary  (source: url)` per item,
  and one test asserting the block is entirely absent when `discussion_evidence=[]`.
- End-to-end: a `NarrativeService` constructed with a stub `discussion_reader` produces a
  user message (captured via `FakeLLMClient`) containing the block; a service constructed
  without one (`discussion_reader=None`, the default) omits it — backward compatibility.
- A shape test confirms the rendered evidence line is exactly
  `- [pain_point] Windows CI is flaky  (source: https://github.com/owner/repo/discussions/1)`,
  i.e. only `DiscussionEvidence` fields appear.
- A prompt test confirms both `_BASE_PROMPT` and `_BASE_INCREMENTAL_PROMPT` (exercised via
  `_generate_full` and `_generate_incremental` respectively) contain the new source-URL
  fidelity instruction.

Full suite: **866 passed, 21 skipped** (was 858 passed / 21 skipped before this batch; +8
new tests, no regressions).

### Gotchas

- `_build_incremental_user_message` already had a defaulted parameter (`use_synopsis: bool =
  False`); the new `discussion_evidence` parameter has no default, so it had to be declared
  *before* `use_synopsis` in the signature (Python requires non-default parameters before
  defaulted ones). Every call site already uses keyword arguments, so this reordering did
  not require touching any caller beyond adding the new argument.
- No existing test called `_build_user_message` / `_build_incremental_user_message`
  directly with positional arguments, so there was no arity-mismatch cleanup needed in the
  existing test suite — all prior coverage exercises these methods indirectly through
  `NarrativeService.generate(...)`.
- `composition.py`'s `build_narrative_service(...)` factory was intentionally **not**
  changed in this batch — it still constructs `NarrativeService` without a
  `discussion_reader`, so discussion evidence does not yet reach production narrative
  generation. Wiring the reader into composition (and the ingest-time fetch/summarize call)
  is the next spec-022 slice.
- Ruff's `UP017` flagged `datetime(..., tzinfo=timezone.utc)` in the new test fixture;
  switched to `datetime(..., tzinfo=UTC)` (`from datetime import UTC, datetime`) to match
  the existing convention in `tests/unit/test_discussions_domain.py`.

### Documentation

- `docs/prompt-contracts/narrative-generation.md` updated with a new "Discussion evidence
  block" section documenting the envelope addition and the source-URL fidelity rule.

### Commits

- `feat: feed discussion evidence into case-study narrative prompt (spec 022)`
