## Batch 122 — Wire embedding computation into commit analysis and discussion evidence (spec 023, slice 5)

### Goal

Wire spec 023's per-item embedding computation (`EmbeddingService`, batch 120) into the two
live places a `CommitAnalysis` or `DiscussionEvidence` is actually produced and persisted: the
commit-analysis write paths (`CommitAnalysisService.analyze_commits` and
`.analyze_commits_async`) and the discussion-evidence ingest flow
(`_fetch_and_store_discussion_evidence` in `api/routes/repos.py`). Before this batch,
`EmbeddingService`/`SemanticSearchService`/the stores all existed but nothing ever called them
outside unit tests — identical situation to discussion evidence before batch 111.

### Why

Same "foundation built, nothing invokes it live" gap spec 023 calls out for the RAG feature: an
`EmbeddedChunk` is only useful if it's computed and stored at the moment a `CommitAnalysis`/
`DiscussionEvidence` is produced. This batch closes that gap without touching retrieval
(`search_similar_commits`, deferred to batch 123) or the evaluation harness (batch 124).

### What was added

**`src/git_it/repository_ingestion/application/ports.py`**
- New `EmbeddingWriter` Protocol: `.save_embeddings(repository_id, items: list[EmbeddedChunk]) ->
  None`. `SqliteEmbeddingStore`/`PostgresEmbeddingStore` (batch 118) already implement this shape
  structurally; this formalizes it as the port `CommitAnalysisService` and the discussion-evidence
  ingest flow depend on, so neither needs to import concrete infrastructure classes.
- New `EmbeddingAnalyzer` Protocol: `.embed_commit_analysis(repository_id, analysis) ->
  EmbeddedChunk | None`. Deviation from the literal batch brief (which specified
  `embedding_service: EmbeddingService | None` as the constructor type): `EmbeddingService` is a
  concrete class, not a Protocol, so mypy rejected test fakes passed to that parameter (nominal
  typing, not structural). Adding this narrow Protocol — mirroring every other dependency
  `CommitAnalysisService` already accepts (`CommitAnalysisWriter`, `RepoContextReader`, etc.) —
  keeps the constructor decoupled from the concrete `EmbeddingService` class and lets test doubles
  stay structurally typed without subclassing it. `EmbeddingService` itself is unchanged and still
  what `composition.py` actually constructs and passes in.

**`src/git_it/repository_ingestion/application/commit_analysis_service.py`**
- `CommitAnalysisService.__init__` gains two optional parameters: `embedding_service:
  EmbeddingAnalyzer | None = None`, `embedding_writer: EmbeddingWriter | None = None`.
- In `analyze_commits`'s sync write path, immediately after `self._analysis_writer.save_analysis(
  ...)`, computes and persists the embedding when both dependencies are present: `chunk =
  self._embedding_service.embed_commit_analysis(repository_id, analysis)`; if not `None`,
  `self._embedding_writer.save_embeddings(repository_id, [chunk])`.
- In `analyze_commits_async`'s internal `_analyze_one` coroutine, the same step is added right
  after the existing `await asyncio.to_thread(self._analysis_writer.save_analysis, ...)` call,
  itself wrapped in `await asyncio.to_thread(...)` (a nested `_embed_and_save` closure) so the
  real network call to the embedding API never blocks the event loop — same reasoning already
  applied to the analysis-save call.
- Neither path's return value, `results` list, or `on_progress` callback is affected — this is a
  pure best-effort side effect alongside persistence, exactly like `analysis_writer.save_analysis`.
  `embed_commit_analysis` already returns `None` on any failure (batch 120); no additional
  try/except was needed at either call site.

**`src/git_it/repository_ingestion/composition.py`**
- `build_commit_analysis_service` now constructs `embedding_client = build_embedding_client()`
  once, then `embedding_service = EmbeddingService(embedding_client) if embedding_client is not
  None else None` and `embedding_writer = build_embedding_store(project_root=project_root) if
  embedding_client is not None else None` — the store is only opened/initialized when there's an
  embedding client to feed it. Both are passed into **both** the `postgres` and default-SQLite
  `CommitAnalysisService(...)` constructions.

**`src/git_it/api/routes/repos.py`**
- New imports: `build_embedding_client`, `build_embedding_store` (from `composition`);
  `EmbeddingService` (from `application.embedding_service`).
- `_fetch_and_store_discussion_evidence` now computes embeddings for the freshly-produced
  `evidence` list right after `store.save_discussion_evidence(repository_id, evidence)`, still
  inside the same outer `try/except Exception` — so it inherits spec 022's best-effort posture
  with no new exception handling. Guarded by `build_embedding_client() is not None`; builds one
  `EmbeddingService` and one embedding store, embeds each evidence item (skipping `None`
  failures via a walrus-filtered list comprehension), and calls `save_embeddings(repository_id,
  chunks)` once with whatever succeeded — or not at all if every item failed.

### Tests added (+11)

`tests/unit/test_commit_analysis_service.py` (+3):
- `test_analyze_commits_saves_embedding_when_service_and_writer_provided` — two commits, both
  embed successfully → `save_embeddings` called once per commit with that commit's chunk.
- `test_analyze_commits_skips_save_when_chunk_is_none` — one commit's embedding fails (fake
  returns `None`) → no `save_embeddings` call for that one, the other still saved.
- `test_analyze_commits_without_embedding_dependencies_does_not_touch_embeddings` — default
  construction (no embedding args) behaves identically to before this batch.

`tests/unit/test_commit_analysis_async.py` (+3): the same three behaviors for
`analyze_commits_async` — `test_async_saves_embedding_when_service_and_writer_provided`,
`test_async_skips_save_when_chunk_is_none`,
`test_async_without_embedding_dependencies_does_not_touch_embeddings`.

`tests/unit/test_repository_ingestion_composition.py` (+2):
- `test_build_commit_analysis_service_wires_embedding_dependencies_when_key_set` —
  `OPENAI_API_KEY` set → `service._embedding_service` is an `EmbeddingService` instance,
  `service._embedding_writer` is not `None`.
- `test_build_commit_analysis_service_embedding_dependencies_none_when_key_absent` —
  `OPENAI_API_KEY` unset → both are `None`.

`tests/unit/test_api_repos.py` (+3):
- `test_fetch_and_store_discussion_evidence_computes_embeddings_when_openai_key_set` — fetcher/
  summarizer/embedding client/store/service all mocked; asserts
  `embed_discussion_evidence(repository_id, evidence)` is called and `save_embeddings(
  repository_id, [chunk])` is called with the real chunk the stub returned.
- `test_fetch_and_store_discussion_evidence_skips_embeddings_when_openai_key_absent` —
  `build_embedding_client` mocked to return `None` → `build_embedding_store` never called.
- `test_fetch_and_store_discussion_evidence_swallows_embedding_exceptions` —
  `build_embedding_client` raises → the outer function still returns without raising, proving it
  inherits the existing best-effort try/except.

Full suite: **946 passed, 24 skipped** (baseline before this batch: 935 passed, 24 skipped; +11
passing, no regressions). Ran the complete suite since this touches
`CommitAnalysisService`/`build_commit_analysis_service`/`_fetch_and_store_discussion_evidence`,
all exercised by many existing analysis/composition/API tests.

Gates: `ruff check .`, `ruff format --check .`, and `mypy src/` all pass clean.

### Gotchas

- `analyze_commits_async`'s embedding step needed its own nested closure
  (`_embed_and_save`) rather than passing `self._embedding_service.embed_commit_analysis`
  directly to `asyncio.to_thread`, because the follow-up conditional `save_embeddings` call also
  needs to run off the event loop and depends on the first call's result — a single
  `to_thread`-wrapped closure keeps both steps on the worker thread together.
- The discussion-evidence embedding step deliberately builds one `EmbeddingService`/store pair
  per call rather than caching it across evidence items — mirrors the existing
  `_fetch_and_store_discussion_evidence` style of constructing dependencies inline, and the
  function is already a one-shot best-effort helper invoked once per ingest.

### Commits

- `feat: compute and persist embeddings during analysis and discussion summarization (spec 023)`
