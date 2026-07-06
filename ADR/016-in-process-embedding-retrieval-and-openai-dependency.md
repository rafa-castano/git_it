# ADR 016: In-Process Embedding Retrieval Instead of pgvector, and a Second External LLM-Adjacent API Dependency (OpenAI)

Status: Accepted
Date: 2026-07-06
Decision makers: TBD

## Context

Spec 023 (RAG-Enhanced Semantic Search for the Ask Tab) introduced the
project's first embedding-based retrieval mechanism, and its own "ADR impact"
section flagged two decisions as crossing the threshold that warrants a
dedicated ADR rather than a spec-level note alone:

1. **A deliberate divergence from ADR 006's original plan.** ADR 006 ("Use
   SQLite for MVP, PostgreSQL+pgvector for Future") explicitly defers
   `pgvector` as future work for exactly this kind of similarity-search need.
   Spec 023 does not act on that deferral — it solves the retrieval need a
   different way: an in-process, backend-agnostic cosine-similarity scan over
   plain JSON-encoded vectors, rather than adopting the pinned-but-unused
   `pgvector` extension. A new ADR is needed to record *why* the deferred plan
   was bypassed rather than picked up, so a future contributor does not read
   ADR 006's "future: pgvector" language and assume it is still the intended
   path for retrieval.
2. **A second external LLM-adjacent API dependency.** Every existing LLM call
   site in this codebase (commit analysis, pattern synthesis, narrative
   generation, discussion summarization, chat) is served by whichever single
   completions provider `LiteLLMLLMClient` is configured for (Anthropic, in
   this project's current configuration). Spec 023 adds a second,
   independent external credential and API surface — OpenAI's embeddings
   API, called through the same `litellm` abstraction but gated on its own
   `OPENAI_API_KEY` — because the primary completions provider does not
   offer an embeddings API. This is a genuinely new external-dependency and
   credential-management decision, distinct from anything ADR 007 (local git
   mining + GitHub MCP/API) or the existing completions wiring already cover.

Both decisions shipped across batches 116-123 (spec 024's observability core
first, since embedding calls needed the same `observe_llm_call` wrapper as
completions calls); this ADR records the decisions already implemented,
closing the deferral spec 023 flagged in its own "ADR impact" section.

## Decision

### 1. Cosine-similarity retrieval is in-process and backend-agnostic, not pgvector

`SemanticSearchService.search()` (`application/semantic_search_service.py`)
loads every persisted `EmbeddedChunk` for a repository via the injected
`EmbeddingReader` port, then computes cosine similarity between the query
vector and every stored vector in pure Python (`_cosine_similarity`, using
only `math.sqrt`/`sum`/`zip` — no numpy, no ANN index), sorts descending, and
returns the top-`k`. At this project's realistic scale (hundreds to low
thousands of short vectors per repository), a linear scan is a
sub-millisecond-to-low-millisecond operation — no approximate-nearest-neighbor
index is warranted for the MVP.

The vector itself is stored as a JSON-encoded array in a plain `TEXT` column
named `vector_json`, in an `embedding_vectors` table keyed by
`(repository_id, source_type, source_id)` and upserted on conflict — the
identical schema in both `infrastructure/sqlite/embeddings.py`'s
`SqliteEmbeddingStore` and `infrastructure/postgres/embeddings.py`'s
`PostgresEmbeddingStore`. Neither store uses a Postgres-specific `vector`
column type or the `pgvector` extension ADR 006 pinned as a dependency; both
backends run the exact same similarity-scan code path in
`SemanticSearchService`, because the data they hand back
(`EmbeddedChunk.vector: list[float]`) is identical either way.

This is a deliberate bypass of ADR 006's deferred plan, not an extension of
it: ADR 006 defers `pgvector` for "future work" once retrieval needs
materialize. Now that a real retrieval need exists (spec 023), the decision
is to *not* pick up that deferred plan, because doing so would make the
feature Postgres-only — directly contradicting the project's local-first,
SQLite-default posture (ADR 005, ADR 010). An in-process scan works
identically on both backends and needs no new database extension, keeping
Git It's "clone the repo, run one process, everything just works" MVP
promise intact even for this new capability.

### 2. OpenAI is a second, independent external LLM-adjacent credential

`LiteLLMEmbeddingClient` (`infrastructure/llm.py`), alongside — not a
modification of — `LiteLLMLLMClient`, wraps `litellm.embedding(model=...,
input=[text])`. Its default model is `text-embedding-3-small`, read from the
`EMBEDDING_MODEL` environment variable (`EMBEDDING_MODEL =
os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")`), following the
existing batch-74 convention of env-var-backed configurable constants.
`litellm` routes an embedding call for this model through OpenAI's API,
requiring `OPENAI_API_KEY` — a credential wholly independent of whichever key
backs primary completions (e.g. `ANTHROPIC_API_KEY`).

`build_embedding_client()` (`composition.py`) is the single source of truth
for "is the RAG feature available": it returns a `LiteLLMEmbeddingClient`
when `OPENAI_API_KEY` is set in the environment, else `None`. Every call site
that depends on embeddings checks this return value and degrades gracefully
rather than failing:

- Commit analysis (`commit_analysis_service.py`) and discussion
  summarization (wired via `_fetch_and_store_discussion_evidence` in
  `api/routes/repos.py`) skip embedding computation entirely when it returns
  `None` — no embedding calls, no partial writes, no error surfaced to the
  ingestion/analysis flow (batch 122).
- `build_chat_service` (`chat/composition.py`) computes
  `include_semantic_search = build_embedding_client() is not None` and passes
  it into `ChatService.__init__`, which only then adds
  `search_similar_commits` to its dispatch table and advertised tool schemas
  (batch 123). When the key is absent, the model never sees this tool at all
  — not a tool that returns an error, but one that is not offered, matching
  how other credential-gated capabilities (e.g. `GITHUB_TOKEN`-gated
  features, specs 019/022) already disappear rather than fail loudly in this
  codebase.

`EmbeddingService.embed_commit_analysis`/`embed_discussion_evidence`
(`application/embedding_service.py`) additionally isolate any *per-call*
embedding failure (rate limit, network error, malformed response) to that one
item, returning `None` rather than raising, so one failed embedding never
aborts the surrounding analysis/summarization batch — mirroring
`DiscussionSummarizer`'s existing per-item isolation. Every embedding call
(and every `search_similar_commits` invocation) goes through
`observe_llm_call` (spec 024), the same structured-logging wrapper already
applied to every completions call site.

## Consequences

### Positive

- Semantic search works identically on SQLite (the default, local-first
  backend) and PostgreSQL, with zero backend-specific retrieval code and no
  new database extension to install, configure, or keep in sync across
  environments.
- The "single source of truth" pattern (`build_embedding_client()`) that
  already gates `GITHUB_TOKEN`-dependent features elsewhere in this codebase
  is reused rather than reinvented, keeping the credential-gating story
  consistent across every optional, credential-dependent capability.
- A future, larger-scale need for approximate-nearest-neighbor search (should
  this project's corpus size ever demand it) can adopt `pgvector` later
  without this ADR having built anything that competes with or must be torn
  out for that path — the current `EmbeddedChunk`/`EmbeddingReader`
  boundary would simply gain a new, ANN-backed implementation behind the
  same port.

### Negative

- A second external API credential (`OPENAI_API_KEY`) must now be documented,
  provisioned, and kept out of logs — one more piece of configuration and
  operational surface than a single-provider setup, even though its absence
  degrades the feature gracefully rather than breaking anything.
- Every analyzed commit and summarized discussion now makes one additional
  paid API call (to OpenAI, not whichever provider serves completions) when
  the feature is enabled, a real cost/latency addition on top of the
  per-commit and per-discussion completions calls already made.
- The in-process linear scan does not scale past this project's realistic
  corpus size (hundreds to low thousands of vectors per repository); a
  repository with a much larger commit/discussion history would need a
  different retrieval strategy, which this ADR does not attempt to solve
  ahead of need.

### Neutral

- This does not change the trust posture for commit/discussion content
  established by ADR 008 (treat repository content as untrusted) or ADR 015
  (summarize untrusted text before use as direct LLM input) — it extends the
  same "only validated, already-summarized text crosses a new external-API
  boundary" discipline to a new destination (the embedding call), never to a
  raw commit message, diff, or raw `Discussion` field.
- This adds a fifth tool to ADR 012's agentic tool-calling loop
  (`search_similar_commits`, alongside `search_commits`, `get_patterns`,
  `get_contributors`, `get_case_study`), following the same "explicit,
  model-chosen tool call" architecture ADR 012 established — not an
  automatic, model-invisible retrieval-augmentation step.

## Alternatives considered

- **Adopt `pgvector` now, per ADR 006's original deferred plan**: rejected —
  this would make semantic search a PostgreSQL-only feature, contradicting
  the project's local-first, SQLite-default MVP posture (ADR 005, ADR 010).
  Every other Git It feature works identically on both backends; making this
  one feature backend-specific would be a regression in that consistency,
  and the project's realistic scale does not need an ANN index yet.
- **A third-party/self-hosted vector database** (e.g. a standalone
  Qdrant/Weaviate/FAISS service): rejected — this would introduce an entirely
  new infrastructure dependency and deployment concern for a corpus size
  (hundreds to low thousands of short vectors) that a linear Python scan
  already handles in sub-millisecond-to-low-millisecond time; it would
  directly work against the local-first, no-container MVP posture (ADR 005).
- **Route embeddings through the same completions provider/credential**:
  rejected — not possible today; the primary completions provider configured
  in this project (Anthropic) does not offer an embeddings API. A future
  provider switch that does offer both could revisit this, but that is not
  the current state, and forcing embeddings through an unrelated provider
  abstraction (rather than `litellm`'s existing multi-provider support)
  would add complexity without removing the underlying two-credential
  reality.
- **Make the RAG feature mandatory (fail loudly without `OPENAI_API_KEY`)**:
  rejected — this would break ingestion, analysis, and the rest of the Ask
  tab for every operator who has not configured a second API key, for a
  feature explicitly scoped as optional and additive. The graceful,
  total-degradation posture (`build_embedding_client() -> None`) matches how
  every other optional, credential-gated capability in this codebase already
  behaves.

## Security impact

- `OPENAI_API_KEY` is never logged, matching the existing convention for
  `GITHUB_TOKEN`/`ANTHROPIC_API_KEY` — only `type(exc).__name__` is logged on
  an embedding-call failure (spec 023's Failure modes table).
- OpenAI's embedding API becomes a second external recipient of Git
  It-derived text: the already-validated `CommitAnalysis`/`DiscussionEvidence`
  summary text (never a raw commit message, diff, or raw `Discussion`
  field — the same untrusted-input boundary ADR 008/015 already established,
  extended to a new destination), plus the Ask-tab user's own question text,
  sent to OpenAI for query embedding. This second data flow (a live user's
  question, not just repository content) is new and is called out in spec
  023's own Security/Privacy considerations sections.
- Embedding vectors are opaque numeric data, not free text — there is no
  prompt-injection surface on the return path from the embedding API the way
  a text completion response could carry one.

## Quality impact

- TDD coverage across batches 116-123: observability wrapper
  (`test_observability.py`), embedding domain model
  (`test_embeddings_domain.py`), `LiteLLMEmbeddingClient`
  (`test_embedding_client.py`), `EmbeddingService`
  per-item failure isolation (`test_embedding_service.py`),
  `SqliteEmbeddingStore`/`PostgresEmbeddingStore` roundtrip and upsert
  (`test_embedding_store_sqlite.py`, extended `test_postgres_adapters.py`),
  `SemanticSearchService` ranking/top-k/empty-corpus/validation behavior
  (`test_semantic_search_service.py`), and the conditional
  `search_similar_commits` tool registration and dispatch
  (`test_chat_tools_semantic_search.py`, extended `test_chat_service.py`,
  new `test_chat_composition.py`).
- Batch 124 adds `evals/semantic_search_eval.py`, the first automated,
  `OPENAI_API_KEY`-gated eval asserting concept recall, no raw-text leakage,
  and relevance-ordering sanity for this retrieval mechanism — the practical
  properties this ADR's design choices are meant to make possible.

## Documentation impact

- `specs/023-rag-semantic-commit-search.md` — the spec this ADR closes the
  deferred ADR-impact item for.
- `docs/adr/index.md` — this ADR's row.
- `docs/prompt-contracts/gitit-gpt-system-prompt.md` — documents the
  conditionally-registered `search_similar_commits` tool and its
  evidence-citation instruction sentence.
- `evals/README.md` — documents the new semantic-search eval.

## Links

- `specs/023-rag-semantic-commit-search.md`
- ADR 006 (Use SQLite for MVP, PostgreSQL+pgvector for Future) — the
  deferred plan this ADR bypasses rather than acts on.
- ADR 005 (Use Local-First No-Container MVP Infrastructure) / ADR 010
  (Accepted Limitations of the Local-First Single-Process MVP) — the
  local-first, backend-parity posture this ADR's in-process design preserves.
- ADR 007 (Use Local Git Mining Plus GitHub MCP) — the prior
  external-API-dependency precedent this ADR's second credential extends.
- ADR 008 (Treat Repository Content as Untrusted) — the untrusted-input
  boundary this ADR extends to embedding-API input.
- ADR 012 (Introduce In-Process Agentic Tool-Calling) — the tool-calling loop
  this ADR adds a fifth tool to.
- ADR 015 (Use GraphQL for GitHub Discussions and Summarize Untrusted Text
  Before Use) — the most recent analogous precedent for an ADR closing a
  spec's own deferred "ADR impact" section.
