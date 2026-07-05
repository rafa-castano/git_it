## Batch 119 — LiteLLMEmbeddingClient (spec 023, slice 2)

### Goal

Add the real embedding client for spec 023 (RAG-Enhanced Semantic Search):
`LiteLLMEmbeddingClient` (wraps `litellm.embedding`, gated on `OPENAI_API_KEY`)
and `build_embedding_client()` (the composition-layer single source of truth
for "is the RAG feature available"). This is the second spec-023 build
slice, built on top of batch 118's domain model + stores; no embedding
persistence or retrieval logic lands here — that follows in batch 120
(`EmbeddingService`) and batch 121 (`SemanticSearchService`).

### Why

Spec 023's open question #1 (exact embedding model name) is resolved here:
`EMBEDDING_MODEL` defaults to OpenAI's `text-embedding-3-small` (low cost,
ample dimensionality for short one-paragraph summaries), as an
env-var-backed constant following the batch-74 convention
(`os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")`) — not
locked forever, but a concrete default that unblocks the rest of the build.

### What was added

**`infrastructure/llm.py`** (extended)
- `EMBEDDING_MODEL` — module-level, env-var-backed constant.
- `LiteLLMEmbeddingClient` — alongside, not a modification of,
  `LiteLLMLLMClient`. Constructor takes `model: str = EMBEDDING_MODEL`,
  stored as `self._model` (required so `observe_llm_call`'s
  `getattr(self_arg, "_model", "unknown")` duck-typed lookup populates the
  log record's `model` field correctly). `.embed(text: str) -> list[float]`
  is decorated with `@observe_llm_call("embedding")` — `"embedding"` is one
  of spec 024's locked `call_site` strings. Calls
  `litellm.embedding(model=self._model, input=[text])` and returns
  `response.data[0]["embedding"]`. Never swallows exceptions or malformed
  response shapes (missing `.data`, empty list) — both propagate naturally
  out of `.embed()`; per spec 023's Failure modes table, treating a
  malformed response as an embedding failure is `EmbeddingService`'s job
  (batch 120), one layer up.

**`composition.py`** (extended)
- `build_embedding_client() -> LiteLLMEmbeddingClient | None` — returns
  `None` when `OPENAI_API_KEY` is unset, else a `LiteLLMEmbeddingClient`
  instance. Placed near the other small `build_*` factories. This is the
  single source of truth for "is the RAG feature available" — every other
  RAG-dependent call site (embedding computation at analysis time, the
  future `search_similar_commits` tool) must check its return value and
  skip/hide entirely when `None`, never construct
  `LiteLLMEmbeddingClient` directly.

### Tests added

- `tests/unit/test_embedding_client.py` (new, 8 tests): mocks
  `litellm.embedding` (mirroring `test_llm_infrastructure_observability.py`'s
  mocking style against this same module) — successful call returns the
  correct vector; `litellm.embedding` receives the configured model and
  `input=[text]`; default model resolves to `EMBEDDING_MODEL`; constructor
  override is stored as `self._model`; the call is observed with
  `call_site="embedding"` and the correct `model` (asserted via `caplog`);
  a raised exception (simulated rate limit) propagates unchanged and the
  observability log records `success=False` with the correct `error_type`;
  two malformed-response-shape cases (missing `.data` → `AttributeError`,
  empty `.data` list → `IndexError`) both raise naturally rather than being
  swallowed.
- `tests/unit/test_repository_ingestion_composition.py` (extended, +2):
  `build_embedding_client()` returns `None` when `OPENAI_API_KEY` is unset
  (`monkeypatch.delenv`); returns a `LiteLLMEmbeddingClient` instance when
  it is set (`monkeypatch.setenv`).

Full suite: **919 passed, 24 skipped** (was 909 passed / 24 skipped before
this batch; +10 passing tests, no regressions).

### Gotchas

- `OPENAI_API_KEY` is currently configured in this environment, but the
  associated OpenAI account has `insufficient_quota` (rate-limited / no
  billing configured). This does not block this batch's implementation or
  tests — every test mocks `litellm.embedding`, so no real API call is ever
  made — but real embedding calls will not succeed until that's resolved on
  the OpenAI account side. Flagging it now so batch 120 (which will
  actually call `.embed()` against real data in integration/eval contexts)
  isn't surprised by it.
- `self._model` naming is load-bearing, not stylistic: `observe_llm_call`'s
  decorator extracts the model name for logging via
  `getattr(self_arg, "_model", "unknown")`. Storing the model under any
  other attribute name would silently degrade the log record's `model`
  field to `"unknown"` without any test failure elsewhere — covered
  explicitly by `test_embed_observed_with_embedding_call_site`.

### Commits

- `feat: add LiteLLMEmbeddingClient and build_embedding_client (spec 023)`
