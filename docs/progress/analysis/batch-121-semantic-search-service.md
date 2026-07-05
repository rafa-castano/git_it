## Batch 121 — SemanticSearchService with cosine-similarity retrieval (spec 023, slice 4)

### Goal

Implement `SemanticSearchService`, the application-layer service that embeds a natural-language
query and ranks a repository's persisted `EmbeddedChunk`s by cosine similarity, returning
evidence-linked `SimilarityResult`s. This is slice 4 of spec 023's build order (domain + stores
→ `LiteLLMEmbeddingClient` → `EmbeddingService` → `SemanticSearchService` → composition wiring →
tool registration); composition wiring and the new chat tool land in batch 122.

### Why

Batch 120 gave the project `EmbeddingService`, which turns already-validated summaries into
persisted `EmbeddedChunk`s. Nothing yet reads that corpus back for retrieval. `SemanticSearchService`
is that boundary: it embeds the caller's query via the same `EmbeddingClient`, loads every stored
vector for the repository via a new `EmbeddingReader` port, and computes cosine similarity in pure
Python — no numpy, no ANN index — matching spec 023's explicit "in-process, backend-agnostic linear
scan" design (Goals #3).

### One locked simplification (orchestrator-directed refinement of spec 023)

Spec 023's Domain concepts section originally described `SimilarityResult` with 5 fields:
`source_type, source_id, evidence_ref, summary_text, score`. Since batch 120 already made
`EmbeddedChunk.source_id` hold the full citation-ready evidence reference directly (the
`commit_sha` for `commit_analysis`, the full `discussion_url` for `discussion_evidence` — see
batch 120's locked decision #2), carrying both `source_id` and `evidence_ref` on `SimilarityResult`
would just duplicate the same value under two names. The orchestrator locked this down before
implementation: **`SimilarityResult` has 4 fields, not 5** — `source_type`, `evidence_ref` (== the
matched chunk's `source_id`), `summary_text` (== the matched chunk's `text`), `score`. This is a
refinement of spec 023's wording, not a silent deviation — documented here and enforced by
`test_search_result_carries_correct_evidence_ref_for_both_source_types`.

### What was added

**`application/ports.py`** (extended)
- New `EmbeddingReader` Protocol: `.get_all_embeddings(repository_id: str) -> list[EmbeddedChunk]`.
  `SqliteEmbeddingStore`/`PostgresEmbeddingStore` (batch 118) already implement this shape
  structurally — this formalizes it as the port `SemanticSearchService` depends on, mirroring
  `DiscussionEvidenceReader`'s style.

**`application/semantic_search_service.py`** (new)
- `SimilarityResult` (frozen dataclass): `source_type: str`, `evidence_ref: str`,
  `summary_text: str`, `score: float` — see locked simplification above.
- `SemanticSearchService(embedding_client, embedding_reader)`:
  - `.search(repository_id, query, top_k=10) -> list[SimilarityResult]`.
  - **Validates first**: `query.strip()` empty → raises `ValueError("query must not be empty")`
    before any embedding call — distinguishing "bad input" from "no matches found" per spec 023's
    explicit acceptance criterion.
  - **Embeds the query**: calls `self._embedding_client.embed(query)`; any exception propagates
    naturally (unlike `EmbeddingService`'s per-item isolation — a failed query embedding means the
    search literally cannot run, so there is nothing sensible to isolate it from).
  - **Loads the corpus**: `self._embedding_reader.get_all_embeddings(repository_id)`; empty corpus
    returns `[]` immediately, no exception.
  - **Computes cosine similarity** in pure Python between the query vector and every stored
    vector: `dot(a, b) / (norm(a) * norm(b))`, with a defensive zero-magnitude guard — either
    vector's norm being exactly `0.0` yields a similarity of `0.0` for that item rather than
    raising `ZeroDivisionError`.
  - **Ranks and truncates**: sorts descending by score, returns the top `top_k`.

### Tests added

`tests/unit/test_semantic_search_service.py` (9 tests), using a stub `EmbeddingClient` (fixed
query vector, tracks calls) and a stub `EmbeddingReader` (fixed `list[EmbeddedChunk]`), mirroring
the `_StubEmbeddingClient` style already used in `test_embedding_service.py`:

- ranking by cosine similarity descending, using hand-computable orthogonal/parallel/opposite unit
  vectors so expected scores are exact (`1.0`, `0.0`, `-1.0`);
- `top_k` truncation, using vectors at distinct angles from the query so only the closest `k` are
  returned, in the right order;
- empty corpus → `[]`, no exception;
- empty (`""`) and whitespace-only (`"   "`) query → `ValueError`, and the embedding client's
  `.embed()` is never called (`client.calls == []`) — validated before embedding, so no API call is
  wasted on bad input;
- each `SimilarityResult.evidence_ref` matches its source chunk's `source_id` for both
  `commit_analysis` and `discussion_evidence` chunks in the same corpus;
- a zero-magnitude stored vector (`[0.0, 0.0]`) does not raise `ZeroDivisionError` and scores
  exactly `0.0`, alongside a normal vector scoring `1.0` in the same corpus;
- default `top_k=10` — 12 chunks with strictly descending, distinguishable scores; calling
  `.search(repo_id, query)` without `top_k` returns exactly the top 10, in descending order;
- `SimilarityResult` is a frozen dataclass with the expected 4 fields (`FrozenInstanceError` on
  mutation attempt).

Full suite: **935 passed, 24 skipped** (was 926 passed / 24 skipped before this batch; +9 new
tests, all in `test_semantic_search_service.py`, no regressions).

### Gotchas

- `ruff` flagged `pytest.raises(Exception)` as a blind-exception assertion (`B017`) in the
  frozen-dataclass test; switched to `pytest.raises(dataclasses.FrozenInstanceError)`, the precise
  exception a frozen dataclass raises on attribute assignment.
- `ruff format` reformatted one line in the test file (a long dict-lookup assertion) — no
  functional change.
- `_cosine_similarity` uses `zip(a, b, strict=True)`, so mismatched query/stored vector dimensions
  raise a `ValueError` rather than silently truncating — not exercised by a dedicated test in this
  batch (out of scope: spec 023 does not call out dimension-mismatch handling), but noted here as
  the current behavior should it come up later (e.g. after an embedding-model change alters
  dimensionality for newly-computed vectors while old ones remain stored).

### Commits

- `feat: add SemanticSearchService with cosine-similarity retrieval (spec 023)`
