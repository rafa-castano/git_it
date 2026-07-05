## Batch 120 — EmbeddingService with per-item failure isolation (spec 023, slice 3)

### Goal

Implement `EmbeddingService`, the application-layer service that turns an already-validated
`CommitAnalysis` or `DiscussionEvidence` into a persisted-ready `EmbeddedChunk`, one embedding
call per item, isolating any single item's embedding failure from the surrounding batch. This
is slice 3 of spec 023's build order (domain + stores → `LiteLLMEmbeddingClient` →
`EmbeddingService` → `SemanticSearchService` → composition wiring → tool registration); the
similarity-search retrieval logic and persistence wiring land in later batches (121, 122).

### Why

Batch 119 gave the project a real `LiteLLMEmbeddingClient` that deliberately never catches its
own exceptions (per its docstring, that's this batch's job). Nothing yet turns a
`CommitAnalysis`/`DiscussionEvidence` into a stored `EmbeddedChunk`. `EmbeddingService` is that
boundary, mirroring `DiscussionSummarizer`'s per-item isolation posture (spec 022, batch 109)
exactly: one embedding call per item, caught and logged as `type(exc).__name__` only, `None`
returned on failure, never aborting the batch.

### Two locked design decisions (orchestrator-directed clarifications of spec 023)

Spec 023's Domain concepts section left two points slightly underspecified. Both were locked
by the orchestrator before this batch started, to avoid ambiguity blocking implementation:

1. **Only `CommitAnalysis.summary` is embedded.** Spec 023 lists `summary`/`summary_beginner`/
   `summary_expert` as candidate embeddable fields but does not lock which. This batch embeds
   only the canonical, always-populated `summary` field — never the optional, audience-specific
   `summary_beginner`/`summary_expert` variants. One `EmbeddedChunk` per commit, not three. This
   avoids embedding three near-duplicate texts per commit (3x embedding cost, and an ambiguous
   choice of which variant a future similarity search should match), and is consistent with the
   spec's "no chunking strategy needed... one short text per commit" framing. Enforced by
   `test_embed_commit_analysis_never_embeds_beginner_or_expert_variant`, which asserts the exact
   string passed to the fake client's `.embed()` equals `analysis.summary` and is never equal to
   either variant field.
2. **`EmbeddedChunk.source_id` holds the full `discussion_url` for `source_type=
   "discussion_evidence"`, not the bare `discussion_id`.** Spec 023 describes `source_id` as
   "the `commit_sha` or `discussion_id` this embedding describes," but a bare numeric
   `discussion_id` alone is not enough to build a citation link later — spec 023's
   `SimilarityResult.evidence_ref` needs the full, already-validated `discussion_url`, and
   re-deriving a GitHub discussion URL from a bare id would require a separate lookup of the
   owning repository's canonical URL at query time. Storing the full URL now avoids that
   fragile, avoidable complexity. For `source_type="commit_analysis"`, `source_id` remains
   `analysis.commit_sha` exactly as originally specified (a bare commit_sha is already
   sufficient elsewhere in this codebase). This makes `source_id`'s practical meaning "the
   citation-ready evidence reference for that source type," a refinement of spec 023's wording
   rather than a silent deviation — enforced by
   `test_embed_discussion_evidence_returns_chunk_with_full_discussion_url_as_source_id`.

### What was added

**`application/embedding_service.py`** (new)
- `EmbeddingService(embedding_client: EmbeddingClient)` — constructor takes only the
  `EmbeddingClient` port, no infrastructure imports (mirrors `DiscussionSummarizer`'s shape).
- `embed_commit_analysis(repository_id, analysis) -> EmbeddedChunk | None` /
  `embed_discussion_evidence(repository_id, evidence) -> EmbeddedChunk | None` — both delegate
  to a shared private `_embed()` helper that calls `self._embedding_client.embed(text)`, wraps
  the call in `try/except Exception`, and on success builds a fully-populated `EmbeddedChunk`
  (`vector` from the client, `created_at=datetime.now(UTC)`).
- **Model name resolution**: `EmbeddedChunk.model` is read via
  `getattr(self._embedding_client, "_model", "unknown")` — the same duck-typed lookup pattern
  already used by `infrastructure/observability.py`'s `_extract_model()` helper for
  `LiteLLMLLMClient`/`LiteLLMEmbeddingClient` (both store their model under `self._model`).
  Chosen over adding a `model` parameter to `embed_commit_analysis`/`embed_discussion_evidence`
  because the `EmbeddingClient` Protocol doesn't expose a model attribute formally, but every
  concrete implementation already stores it as `self._model` for `observe_llm_call`'s benefit —
  reusing that existing convention avoids widening either method's public signature.
- **Failure isolation**: on any exception from `.embed()`, catches it with
  `except Exception as exc: # noqa: BLE001` (mirroring `DiscussionSummarizer._summarize_one`'s
  exact posture — this is a boundary call to a third-party API, so a broad catch is intentional,
  not sloppy), logs `_logger.warning("embedding failed: %s", type(exc).__name__)`, and returns
  `None`. Never logs the exception message, args, or the text being embedded.
- **Non-goals compliance**: only `analysis.summary` / `evidence.summary` are ever passed to
  `.embed()` — no raw commit message, diff, or raw `Discussion` field reaches this layer at all
  (there is no raw `Discussion` object in scope here; the boundary is enforced one layer up by
  `DiscussionSummarizer` producing `DiscussionEvidence` in the first place).

### Tests added

`tests/unit/test_embedding_service.py` (7 tests), using a stub `EmbeddingClient` with scripted
per-call responses (mirrors `_StubLLMClient` in `test_discussion_summarizer.py`):

- successful `embed_commit_analysis` → `EmbeddedChunk` with `source_type="commit_analysis"`,
  `source_id == analysis.commit_sha`, `text == analysis.summary`, correct `vector`;
- **locked decision #1 test**: the exact string passed to `.embed()` is `analysis.summary` and
  is never `summary_beginner`/`summary_expert`;
- successful `embed_discussion_evidence` → `EmbeddedChunk` with
  `source_type="discussion_evidence"`, `source_id == evidence.discussion_url` (asserted `!=
  evidence.discussion_id` to prove it's the full URL, not the bare id — locked decision #2),
  `text == evidence.summary`;
- only `evidence.summary` is ever passed to `.embed()` for discussion evidence;
- `.embed()` raising for a commit analysis → returns `None`; `caplog` asserts only
  `"RuntimeError"` appears in the log, never the exception's message/args or the summary text
  that was being embedded;
- same failure-isolation/log-redaction assertion for `embed_discussion_evidence`;
- a batch of three commit analyses where the middle one's `.embed()` raises → the other two
  still return populated `EmbeddedChunk`s with the correct `source_id`s, proving one failure
  doesn't abort the batch (mirrors `DiscussionSummarizer`'s equivalent test).

Full suite: **926 passed, 24 skipped** (was 919 passed / 24 skipped before this batch; +7 new
tests, all in `test_embedding_service.py`, no regressions).

### Gotchas

- `ruff format` required wrapping the stub client's `__init__` signature across two lines (the
  single-line form exceeded the 100-char line limit) — no functional change.
- The `_embed()` private helper's `source_type` parameter is typed as plain `str`, requiring a
  `# type: ignore[arg-type]` at the `EmbeddedChunk(...)` construction site, since
  `EmbeddedChunk.source_type` is `Literal["commit_analysis", "discussion_evidence"]`. Both
  public methods (`embed_commit_analysis`/`embed_discussion_evidence`) pass a literal string at
  their own call sites, so the actual values are always one of the two allowed literals — the
  ignore only concerns the shared helper's necessarily-widened internal signature, not the
  public contract.

### Commits

- `feat: add EmbeddingService with per-item failure isolation (spec 023)`
