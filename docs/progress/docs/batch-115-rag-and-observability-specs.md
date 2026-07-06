## Batch 115 — Specs 023 (RAG semantic search) and 024 (LLM call observability)

### Goal

The user proposed two new capabilities in one message: (1) letting the Ask tab answer
conceptual questions about individual historical commits by vectorizing commit/discussion
summaries for retrieval, and (2) instrumenting all LLM calls with monitoring, possibly via
Langfuse. Both are new-feature/architecture/LLM-prompt/data-model territory, so per CODEX.md
this triggered the `grill-me-with-docs` protocol before any implementation — this batch is
**spec-only**, no production code changes ship here.

### What was checked before asking anything

Delegated a narrow Explore-agent recon (4 files, at the mandatory-delegation threshold) covering:
the current Ask-tab/GitItGPT architecture (agentic tool-calling, ADR 012, 4 existing read-only
tools, no chunking/pagination beyond a `limit` param, no retrieval mechanism of any kind); the
LLM client abstraction (5 distinct client classes across `infrastructure/llm.py` and
`chat/litellm_client.py`, no shared instrumentation choke point); the exact shape of
`CommitAnalysis`/`DiscussionEvidence` as candidate RAG corpus material, plus real row counts in
the local dev database (241 analyzed commits, 2 discussion-evidence rows); existing dependencies
(`pgvector` is pinned in `pyproject.toml` but ADR 006 explicitly defers it — no vector column,
extension, or index exists anywhere; no observability library present); and existing ADRs/specs
(ADR 006 defers pgvector, ADR 012 establishes the tool-calling architecture, ADR 015 establishes
the "validated-summary-only, never raw text" boundary that any RAG corpus must inherit; no ADR or
spec mentions Langfuse/observability at the per-call level — spec 012's own Observability section
is one aggregate per-request log line, nothing per-call).

Also checked (boolean only, no values printed) which embedding-capable provider keys are already
configured locally: only `ANTHROPIC_API_KEY` is set, and Anthropic has no embeddings API — this
directly shaped one of the grill questions.

### Questioning round (grill-me-with-docs)

Two rounds of `AskUserQuestion` (4 + 2 questions), all answered:

1. **RAG backend**: SQLite-compatible (in-process cosine similarity, no pgvector) — the default
   backend must not lose the feature.
2. **RAG's actual goal**: semantic/conceptual search — closing the gap that today's exact
   category/date filters cannot match a *concept*.
3. **RAG corpus scope**: only already-validated summaries (`CommitAnalysis.summary`/
   `summary_beginner`/`summary_expert`, `DiscussionEvidence.summary`) — never raw commit
   messages/diffs or raw `Discussion` fields, preserving ADR 008/015.
4. **Embedding provider**: OpenAI (via `litellm`), since Anthropic has no embeddings API — this
   is a **new** external dependency and a **new** required credential (`OPENAI_API_KEY`, not yet
   configured), which the spec locks as gracefully-degrading (feature hidden entirely when the
   key is absent, same posture as `GITHUB_TOKEN`-gated features).
5. **Observability approach**: no Langfuse for now — structured JSON logs only, so a real tool can
   be layered on later without re-instrumenting every call site.
6. **Log content**: metadata only (model, tokens, latency, cost, call site, success/error) —
   never prompt/response content, consistent with CODEX.md's "don't log secrets/untrusted
   content" posture.

### What was added

- `docs/specs/023-rag-semantic-commit-search.md` (new, Draft) — full grill-me-with-docs template:
  domain concepts (`EmbeddedChunk`, `EmbeddingClient`, `LiteLLMEmbeddingClient`,
  `SqliteEmbeddingStore`/`PostgresEmbeddingStore`, `EmbeddingService`, `SemanticSearchService`,
  new `search_similar_commits` tool), 8 Gherkin acceptance criteria, failure-mode table, security/
  privacy sections (OpenAI as a new third-party recipient of both repo-derived summaries *and*
  the user's own Ask-tab question text — flagged explicitly), full test list, a new eval
  (`evals/semantic_search_eval.py`, concept-recall + no-leakage + relevance-ordering checks), and
  an ADR-impact assessment (new ADR warranted: first embedding-retrieval mechanism, and a
  deliberate divergence from ADR 006's pgvector plan in favor of in-process, backend-agnostic
  search). Three explicit Open questions (embedding model/dimension, default `top_k`,
  re-embedding-on-re-analysis) left unlocked rather than guessed at.
- `docs/specs/024-llm-call-observability.md` (new, Draft) — `LLMCallObservation` dataclass,
  `observe_llm_call(call_site)` wrapper/decorator applied to all 5 existing LLM call sites (plus
  spec 023's embedding client once built), 5 Gherkin ACs including the two hardest-to-get-wrong
  ones (a logging failure must never break the underlying call; content must never leak into the
  log record), full test list, and an explicit "likely not ADR-worthy on its own" assessment
  (revisit if/when a real tool like Langfuse is added later — that decision would cross the ADR
  threshold, this one doesn't).
- `docs/specs/index.md` — added rows for 023/024 (Draft), keeping the index in sync going
  forward rather than letting it go stale again (batch 114 just fixed this same staleness for
  015-022).

### Tests added

None — this batch is spec-authoring only, no production code or tests. Both specs' own "Tests
required" sections define the TDD order a future build batch must follow.

### Gate

`uv run --group docs mkdocs build --strict` — exit 0, no new warnings (specs/ files live at the
repo root, outside the mkdocs `docs/` tree, so only the `docs/specs/index.md` edit is in scope
for this gate).

### Gotchas

- Both proposed features arrived bundled in one user message but are architecturally
  independent (different corpora, different external dependencies, different risk profiles) —
  written as two separate specs rather than one combined one, so each can be built/reviewed/
  ADR'd on its own timeline.
- The RAG spec deliberately does **not** revisit ADR 006's pgvector deferral — it solves the
  retrieval need a different way (in-process search) specifically because the SQLite-first grill
  answer ruled out requiring Postgres for this feature to work at all.
- The observability spec is intentionally the *lighter* of the two (no new dependency, no new
  external service) per the grill answer — it's scoped as a foundation that a future Langfuse (or
  other tool) integration could sit on top of without re-touching the five call sites again.

### Commits

- `docs: add spec 023 (RAG semantic search) and spec 024 (LLM call observability)`
