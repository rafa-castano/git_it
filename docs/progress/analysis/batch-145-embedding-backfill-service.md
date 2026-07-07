## Batch 145 — EmbeddingBackfillService and composition wiring (spec 027, slice 1)

### Goal

Implement the core application service that backfills embeddings for already-stored
`commit_analyses`/`discussion_evidence` evidence that predates `OPENAI_API_KEY` being
configured. This is slice 1 of spec 027's build order (backfill service → CLI command →
API endpoint + progress → dashboard control); the CLI command, budget-guardrail
confirmation prompt, API endpoint, and dashboard control are explicitly out of scope and
land in later batches (146, 147).

### Why

Git It's semantic-search feature (spec 023) only works over content embedded *at analysis
time*. Anything analyzed before an OpenAI key was present has a persisted
`CommitAnalysis`/`DiscussionEvidence` row but no matching `embedding_vectors` row, and
nothing ever fills that gap — the README explicitly documented this as a known limitation.
This batch adds the orchestrator that enumerates already-stored evidence, computes the
missing subset relative to what's already embedded, and embeds only that subset — full
parity with what the live pipeline embeds (both `commit_analysis` and
`discussion_evidence`, nothing more), reusing `EmbeddingService`'s existing per-item
failure isolation posture.

### What was added

**`application/embedding_backfill_service.py`** (new)
- `BackfillEmbedder` — a local `Protocol` with `embed_commit_analysis` and
  `embed_discussion_evidence`, mirroring `EmbeddingService`'s two public methods
  structurally. Spec 027 proposed depending on "an `EmbeddingAnalyzer`-shaped embedder,"
  but the existing `EmbeddingAnalyzer` Protocol in `ports.py` only declares
  `embed_commit_analysis` (it was scoped to `CommitAnalysisService`'s needs) — it does not
  cover `embed_discussion_evidence`, which this service also needs. Rather than widen the
  shared `EmbeddingAnalyzer` port (out of scope for this slice, and used elsewhere), a
  local Protocol combining both methods was defined in this new module.
  `EmbeddingService` satisfies it structurally without any changes — noted here as the one
  deviation from the spec's exact wording.
- `EmbeddingBackfillResult` — frozen dataclass with `embedded`, `already_present`, `failed`
  counts, matching spec 027's Observability section ("embedded N, skipped M,
  already-present K").
- `EmbeddingBackfillService(commit_analysis_reader, discussion_evidence_reader,
  embedding_reader, embedding_writer, embedder)` — all keyword-only, depends only on ports
  (`CommitAnalysisReader`, `DiscussionEvidenceReader`, `EmbeddingReader`, `EmbeddingWriter`
  from `application/ports.py`) plus the new `BackfillEmbedder` Protocol.
  - `estimate_backfill_calls(repository_id) -> int` — the exact method name spec 027 locks
    in its Domain Concepts and Tests Required sections (mirroring the *shape* of
    `CommitAnalysisService.estimate_llm_calls`, a different quantity). Returns the count of
    items missing an embedding, computed the same way `backfill()` computes it, without
    calling the embedder. Returns `0` when `embedder is None`.
  - `backfill(repository_id) -> EmbeddingBackfillResult` — enumerates
    `CommitAnalysisReader.list_analyses(repository_id, limit=None)` and
    `DiscussionEvidenceReader.get_discussion_evidence(repository_id)`, subtracts the set of
    `(source_type, source_id)` pairs already present in
    `EmbeddingReader.get_all_embeddings(repository_id)`, embeds only the complement via the
    injected embedder, and persists the non-`None` results in one
    `EmbeddingWriter.save_embeddings` call (skipped entirely when nothing was embedded).
    Returns `EmbeddingBackfillResult(embedded=0, already_present=0, failed=0)` immediately
    when `embedder is None` — the no-key clean no-op (spec 027 Goal 4).
  - Source-id keying matches the live pipeline exactly: `commit_analysis` keys on
    `analysis.commit_sha`, `discussion_evidence` keys on `evidence.discussion_url` (never
    the bare `discussion_id`) — the same locked decision `EmbeddingService` already
    enforces, verified here independently since this service reads `discussion_url`
    directly to compute the missing set.
  - **Per-item failure isolation implemented at this layer too**, not merely inherited:
    `_safe_embed_commit_analysis`/`_safe_embed_discussion_evidence` wrap each call to the
    injected embedder in `try/except Exception`, log
    `_logger.warning("embedding backfill failed: %s", type(exc).__name__)` (never the raw
    exception or the text being embedded), and count the item as `failed` without aborting
    the batch. This matters because `embedder` is a Protocol — a future or test embedder
    that raises instead of returning `None` still can't take down the batch, even though
    the concrete `EmbeddingService._embed` already isolates its own failures.

**`composition.py`**
- New import: `EmbeddingBackfillService` from the new module.
- `build_embedding_backfill_service(*, project_root) -> EmbeddingBackfillService` — mirrors
  `build_commit_analysis_service`'s embedding-wiring pattern exactly: calls
  `build_embedding_client()`, wraps it in `EmbeddingService(embedding_client)` only if not
  `None`, and wires `build_commit_analysis_reader`, `build_discussion_evidence_store`, and
  one shared `build_embedding_store(project_root=project_root)` instance for both the
  reader and writer role (that store already implements both `EmbeddingReader` and
  `EmbeddingWriter`). Backend-aware via the existing `_get_db_backend()` indirection inside
  those builder functions — no new backend branching needed in this factory itself. Returns
  a service whose `embedder` is `None` (clean no-op) whenever `OPENAI_API_KEY` is unset,
  never raising.

### Tests added

`tests/unit/test_embedding_backfill_service.py` (6 tests, new file), using hand-rolled
fakes for every port (no real DB, no network) mirroring the injection style of
`test_semantic_search_service.py`:
- `_StubCommitAnalysisReader` / `_StubDiscussionEvidenceReader` — keyed by
  `repository_id`, so cross-repository isolation can be exercised directly.
- `_FakeEmbeddingStore` — a combined `EmbeddingReader`/`EmbeddingWriter` fake that
  replicates the real store's `(repository_id, source_type, source_id)` upsert semantics,
  so idempotency is exercised end-to-end against fakes only.
- `_FakeEmbedder` — scriptable per-`commit_sha`/`discussion_url` failures (raises
  `RuntimeError` for scripted keys, returns a populated `EmbeddedChunk` otherwise).

Tests:
- `test_count_missing_counts_analyses_and_evidence_without_an_embedding` — 8 analyses + 3
  discussion items, 2 analyses already embedded → `estimate_backfill_calls` returns exactly
  9.
- `test_backfill_embeds_only_items_missing_an_embedding` — asserts the embedder is called
  only for the missing `sha2`/discussion item, not for the already-embedded `sha1`; result
  counts (`embedded=2`, `already_present=1`, `failed=0`) and persisted rows are checked.
- `test_second_backfill_run_is_idempotent_and_embeds_nothing` — a second `backfill()` call
  against the same (fake) store makes zero new embedder calls and reports
  `embedded=0, already_present=3`.
- `test_one_failing_item_does_not_prevent_others_from_being_embedded` — one commit
  analysis's embed raises; the other two are still persisted, `failed == 1`, and `caplog`
  asserts only `"RuntimeError"` appears — the raw summary text and the word `"boom"` never
  do.
- `test_backfill_with_no_embedder_is_a_clean_no_op` — `embedder=None` → zero-count result,
  no writes, `estimate_backfill_calls` returns 0, no exception raised.
- `test_missing_item_in_one_repository_does_not_affect_another` — a missing item in
  `repo-a` and an already-embedded item in `repo-b` are computed and acted on
  independently; backfilling `repo-a` never touches `repo-b`'s stored rows.

`tests/unit/test_repository_ingestion_composition.py` (+2 tests):
- `test_build_embedding_backfill_service_wires_embedder_when_key_set` — with
  `OPENAI_API_KEY` set, `service._embedder` is an `EmbeddingService` instance.
- `test_build_embedding_backfill_service_embedder_none_when_key_absent` — without the key,
  `service._embedder is None` and `estimate_backfill_calls` returns 0.

All new tests were RED before implementation existed (`ModuleNotFoundError` /
`ImportError` on the new symbols), then GREEN after each corresponding implementation
step, per this project's TDD discipline.

Full suite: **1110 passed, 33 skipped** (was 1100 passed / 33 skipped before this batch;
+8 new tests across the two files above, no regressions).

### Gotchas

- `ruff format --check` initially disagreed with `_missing_items`'s wrapped
  `already_present` expression and both new files' import ordering — `ruff format` (applied
  in place) resolved both; no functional change.
- The first draft of `test_embedding_backfill_service.py` used ad-hoc fake discussion URLs
  (`https://x/1`) — `DiscussionEvidence` validates `discussion_url` against the
  `https://github.com/{owner}/{repo}/discussions/{number}` pattern via a Pydantic
  `field_validator`, so all fake URLs had to match that shape. Fixed to
  `https://github.com/owner/repo/discussions/{n}`.
- `_missing_items` is computed once per `backfill()`/`estimate_backfill_calls()` call and
  returns `(missing_analyses, missing_evidence, already_present_count)` in one pass over
  both readers, avoiding a second read of the same evidence just to compute
  `already_present` separately.
- Confirmed no CLI/API/static files were touched — this batch is scoped strictly to the
  application service and its composition factory, per spec 027's build order.

### Commits

- (staged, not committed by this batch — orchestrator will review and commit)
