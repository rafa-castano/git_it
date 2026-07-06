## Batch 142 — Cite release and advisory evidence in the case-study narrative (spec 026, slice 6)

### Goal

Wire the schema-validated `ReleaseEvidence` and `AdvisoryEvidence` items (domain: batch 137;
fetchers: batch 138; summarizers: batch 139; stores: batch 140; ingest wiring: batch 141) into
`NarrativeService` so both the full and incremental narrative-generation prompts can cite
release history and security-advisory facts alongside commit, discussion, and project-doc
evidence. This is the final slice of spec 026's build order (domain → fetchers → summarizers →
stores → ingest wiring → narrative).

### Why

`ReleaseEvidenceReader`/`AdvisoryEvidenceReader`-shaped stores already existed (batch 140) and
were already populated during ingestion (batch 141), but nothing in the narrative path read
them — release and advisory evidence was persisted but never reached the LLM prompt. This
batch closes that gap, mirroring the exact pattern spec 022 established for
`DiscussionEvidence` (batch 110).

### What was added

**`application/ports.py`**
- Two new Protocols mirroring `DiscussionEvidenceReader`: `ReleaseEvidenceReader`
  (`get_release_evidence(repository_id) -> list[ReleaseEvidence]`) and
  `AdvisoryEvidenceReader` (`get_advisory_evidence(repository_id) -> list[AdvisoryEvidence]`).
  The existing SQLite/PostgreSQL stores (batch 140) already implement these shapes
  structurally, so no store changes were needed.

**`application/narrative_service.py`**
- `NarrativeService.__init__` gained two optional, keyword-only dependencies:
  `release_evidence_reader: ReleaseEvidenceReader | None = None` and
  `advisory_evidence_reader: AdvisoryEvidenceReader | None = None`, following the exact pattern
  of `discussion_reader`/`project_doc_reader`. `None` is fully backward compatible — no
  release/advisory evidence is read or rendered.
- `_generate_full` and `_generate_incremental` both read
  `self._release_evidence_reader.get_release_evidence(repository_id)` and
  `self._advisory_evidence_reader.get_advisory_evidence(repository_id)` (or `[]` when no
  reader is configured) and pass both lists into the corresponding `_build_*_user_message`
  method.
- `_build_user_message` and `_build_incremental_user_message` each gained
  `release_evidence: list[ReleaseEvidence] | None = None` and
  `advisory_evidence: list[AdvisoryEvidence] | None = None` parameters (defaulted, placed
  after `project_docs`, so every existing call site keeps working unchanged).
- Two new module-level helpers, `_append_release_evidence_block` and
  `_append_advisory_evidence_block`, append `## Release History` and `## Security Advisories`
  blocks immediately after the existing Discussion Evidence / Project Documentation blocks,
  right before the closing `[/REPOSITORY DATA]` tag:
  - `- [{claim_type}] {summary}  (source: {release_url})` per `ReleaseEvidence` item.
  - `- [{severity}] {summary}  (source: {advisory_url})` per `AdvisoryEvidence` item — labeled
    by GitHub's own `severity` enum rather than a free-form `claim_type`, so a
    prompt-injected advisory description cannot inflate/deflate the reported severity.
  Both are no-ops on an empty list — the `[REPOSITORY DATA]` envelope is byte-identical to
  pre-batch-142 output for repositories with no release/advisory evidence.
- The existing source-URL fidelity sentence in both `_BASE_PROMPT` and
  `_BASE_INCREMENTAL_PROMPT` was generalized to name all three cited-evidence blocks: any
  claim derived from the Discussion Evidence, Release History, or Security Advisories blocks
  must repeat the exact `source:` URL given for that item, and the model must not state a
  claim derived from any of those blocks for which no source URL was provided.
- The block is built only from `ReleaseEvidence`/`AdvisoryEvidence` fields — there is no
  `Release`/`SecurityAdvisory` (raw, ephemeral) object in scope in this layer at all, so raw
  release-notes/advisory-description text cannot leak into the prompt by construction.

**`composition.py`**
- `build_narrative_service` now passes
  `release_evidence_reader=build_release_evidence_store(project_root=project_root)` and
  `advisory_evidence_reader=build_advisory_evidence_store(project_root=project_root)` in both
  the Postgres and SQLite branches (both builder functions already existed from batch 141).

### Tests added

`tests/unit/test_narrative_service.py` (+12 tests, all green):
- `_build_user_message` / `_build_incremental_user_message` each get one test per new block
  asserting `## Release History` / `## Security Advisories` renders with
  `[claim_type|severity] summary  (source: url)` per item, and one test asserting the block
  is entirely absent when the corresponding evidence list is empty.
- End-to-end: a `NarrativeService` constructed with stub `release_evidence_reader` and
  `advisory_evidence_reader` produces a user message (captured via `FakeLLMClient`) containing
  both blocks with their source URLs; a service constructed without them (both `None`, the
  default) omits both — backward compatibility.
- Shape tests confirm the rendered evidence lines are exactly
  `- [feature_release] Added semantic search.  (source: https://github.com/owner/repo/releases/tag/v1.0.0)`
  and
  `- [high] Path traversal patched.  (source: https://github.com/owner/repo/security/advisories/GHSA-aaaa-bbbb-cccc)`,
  i.e. only `ReleaseEvidence`/`AdvisoryEvidence` fields appear.
- A prompt test confirms both `_BASE_PROMPT` and `_BASE_INCREMENTAL_PROMPT` (exercised via
  `_generate_full`/`_generate_incremental`) name Release History and Security Advisories in
  the source-URL fidelity instruction.

Full suite: **1100 passed, 33 skipped** (was 1088 passed / 33 skipped before this batch; +12
new tests, no regressions).

### Gotchas

- Both `_build_user_message` and `_build_incremental_user_message` already had a defaulted
  `project_docs` parameter; the new `release_evidence`/`advisory_evidence` parameters were
  added after it (also defaulted to `None`, normalized to `[]` with `... or []` at the call
  site) so no existing positional-argument test call broke.
- `AdvisoryEvidence` uses `severity` (a `Literal["low", "medium", "high", "critical"]`) instead
  of `claim_type` for its evidence line — deliberately different from
  `DiscussionEvidence`/`ReleaseEvidence`, matching the domain model's own security-conscious
  design (spec 026: severity is validated against GitHub's known enum, not trusted as
  arbitrary LLM output).
- `composition.py`'s `build_release_evidence_store`/`build_advisory_evidence_store` factories
  already existed from batch 141 (for ingest-time persistence) — this batch only adds them as
  the narrative service's readers, no store/builder changes were needed.

### Documentation

- `docs/prompt-contracts/narrative-generation.md` gained two new sections, "Release history
  block" and "Security advisories block", mirroring the existing "Discussion evidence block"
  section, and the "Source-URL fidelity rule" paragraph was extended to name all three blocks.

### Commits

- `feat: cite release and advisory evidence in case study narrative (spec 026)`
