# Feature Spec: RAG-Enhanced Semantic Search for the Ask Tab

**Status:** Draft
**Spec number:** 023
**Author:** Rafael Castaño
**Date:** 2026-07-05

---

## Summary

Add a new tool, `search_similar_commits`, to GitItGPT's existing agentic tool-calling loop
(ADR 012), backed by an in-process (no pgvector, no external vector database) cosine-similarity
index over embeddings of already-validated `CommitAnalysis` and `DiscussionEvidence` summaries.
Embeddings are computed via OpenAI's embedding API (through `litellm`, consistent with this
project's existing provider-agnostic LLM client pattern) at analysis/summarization time and
persisted alongside the records they describe, on both the SQLite and PostgreSQL backends. This
lets the Ask tab answer conceptual questions — "what security mistakes were made early in the
project," "find commits about flaky tests" — that today's exact category/date filters cannot
match, while preserving every existing evidence-citation and untrusted-input discipline this
codebase already enforces (ADR 008, ADR 015).

---

## Problem

GitItGPT (spec 012) already answers repository questions through four deterministic, repo-scoped
tools: `search_commits` (category/order/limit filter), `get_patterns` (pre-computed hotspots and
signals), `get_contributors`, and `get_case_study` (a pre-synthesized narrative). None of these
can answer a *conceptual* question — one that doesn't share an exact category label or date range
with the commits that actually answer it. Asking "what mistakes were made in the early days"
today can only be approximated via `search_commits(order="oldest", limit=20)`, which:

1. Has no notion of "mistake" as a concept — it filters by `category`/`order`/`limit`, not by
   meaning.
2. Returns whatever page of commits the model happens to request, with no chunking or
   progressive summarization — the entire tool result is stuffed into the prompt as-is
   (`chat/service.py`), so a large `limit` on a repository with hundreds or thousands of commits
   risks blowing the context window well before the model's `turn_cap` (default 6) is reached.
3. Cannot combine evidence from *both* commits and discussions (spec 022) under one conceptual
   query — a design decision or recurring pain point captured in a GitHub Discussion has no path
   into an answer about "early mistakes" unless the model happens to also call `get_case_study`.

Semantic (embedding-based) retrieval closes exactly this gap: it lets a natural-language query
match commits/discussions by meaning, independent of exact keywords, category labels, or manual
pagination.

---

## Goals

1. New tool `search_similar_commits(query: str, top_k: int = 10)`, added to the existing
   `READ_ONLY_TOOLS` set (`tools/registry.py`) alongside the four tools already there — the model
   *chooses* to call it, exactly like every other tool; this is not a silent, automatic
   context-injection mechanism.
2. Embeddings are computed once, at analysis/summarization time — for every `CommitAnalysis`
   (right after it's produced) and every `DiscussionEvidence` (right after it's produced) — and
   persisted, mirroring the "compute once, persist" discipline already used for those records
   themselves.
3. Retrieval is a pure in-process cosine-similarity scan over persisted vectors, stored as
   JSON-encoded float arrays in an ordinary text column — **no pgvector, no new database
   extension, no external vector-store service** — so it behaves identically on the SQLite
   (default) and PostgreSQL backends. At this project's realistic scale (hundreds to low
   thousands of commits per repository), a linear scan of a few thousand short vectors is a
   sub-millisecond-to-low-millisecond operation; no ANN index is warranted for the MVP.
4. Embeddings are generated via OpenAI's embedding API, called through `litellm.embedding(...)`
   (the same multi-provider abstraction already used for completions in
   `infrastructure/llm.py`), gated on a new `OPENAI_API_KEY` environment variable — a **second**
   external LLM-adjacent credential, distinct from whatever provider key backs the primary
   analysis/narrative/chat models (Anthropic, in this project's current configuration, which
   does not offer an embeddings API).
5. Every result `search_similar_commits` returns carries its evidence reference (`commit_sha` or
   `discussion_url`) back to the caller, so an LLM answer built from a similarity result stays
   evidence-linked exactly like every other Git It claim (CODEX.md's evidence-before-interpretation
   principle).
6. Graceful, total degradation when `OPENAI_API_KEY` is absent: no embedding calls are ever made,
   no embeddings are stored, and `search_similar_commits` is **not registered** into the tool set
   offered to the LLM at all (not merely a tool that returns an error) — identical in spirit to
   how `GITHUB_TOKEN`-gated features (spec 019, spec 022) disappear rather than fail loudly.

---

## Non-goals

- Vectorizing raw commit messages, diffs, or raw `Discussion` title/body/answer text. Only
  already-validated, LLM-produced summary text is ever embedded: `CommitAnalysis.summary` /
  `summary_beginner` / `summary_expert`, and `DiscussionEvidence.summary`. This preserves the
  "validate untrusted text into a schema-checked output before it is used for anything
  downstream" boundary already established by ADR 008 and ADR 015 — extending that same
  boundary to a new destination (an embedding API call) rather than reopening it.
- PostgreSQL's `pgvector` extension or any ANN (approximate nearest neighbor) indexing. ADR 006
  already defers this; this spec deliberately does not revisit that deferral — it solves the
  retrieval need a different way (in-process, backend-agnostic) rather than acting on the pinned
  but unused `pgvector` dependency.
- An automatic, model-invisible retrieval-augmentation step that injects context before every
  chat turn. `search_similar_commits` is one more explicit tool the LLM can decide to call,
  exactly like `search_commits`/`get_patterns`/etc. — preserving ADR 012's "the model explicitly
  decides which read-only tool to call" architecture.
- Backfilling embeddings for repositories analyzed before this feature ships. Same accepted gap
  as specs 019/022: such repositories have no stored embeddings until re-analyzed, and
  `search_similar_commits` simply returns an empty result set for them.
- Chunking or splitting long text before embedding. `CommitAnalysis`/`DiscussionEvidence`
  summaries are already short (one sentence to a short paragraph) — no chunking strategy is
  needed at this corpus scale.
- Any change to the *existing* four tools (`search_commits`, `get_patterns`, `get_contributors`,
  `get_case_study`) or to `CommitAnalysis`/`DiscussionEvidence`'s own schemas beyond adding a new,
  separate embedding-storage table.
- A UI surface for browsing embeddings/similarity scores directly — this feeds the LLM's tool
  loop only; no new REST endpoint or frontend view is introduced by this spec.

---

## Users

- **Learner**: asking the Ask tab a conceptual question about the project's history — "what
  went wrong early on," "find commits related to authentication bugs" — wants a relevant,
  evidence-linked answer even when no exact category/keyword match exists.
- **Operator**: running ingestion/analysis, wants embedding generation to be entirely optional
  (absent `OPENAI_API_KEY`, nothing changes) and never able to block or fail an analysis run.

---

## User stories

1. **As a learner**, when I ask a conceptual question that doesn't map to an exact commit category
   or date range, I want the Ask tab to still find and cite the most relevant commits/discussions
   by meaning, not just by keyword.
2. **As a learner**, I want every claim built from a semantic-search result to link back to the
   specific commit or discussion it came from, so I can verify it myself.
3. **As an operator**, when `OPENAI_API_KEY` is not set, I want ingestion, analysis, and the rest
   of the Ask tab to work exactly as they do today, with no error, no missing functionality
   beyond the absence of this one optional tool.
4. **As an operator**, when the embedding API call fails for one commit or discussion (rate
   limit, network error, malformed response), I want that single item's embedding to simply be
   missing — never an aborted analysis run.

---

## Acceptance criteria

```gherkin
Feature: RAG-enhanced semantic search for the Ask tab

  Scenario: Embedding computed and persisted alongside a new CommitAnalysis
    Given OPENAI_API_KEY is set
    When a commit is analyzed and a CommitAnalysis is produced
    Then an embedding is computed from its summary text
    And the embedding is persisted, keyed to that commit's repository_id and commit_sha

  Scenario: Embedding computed and persisted alongside new DiscussionEvidence
    Given OPENAI_API_KEY is set
    When a DiscussionEvidence item is produced by the discussion summarizer
    Then an embedding is computed from its summary text
    And the embedding is persisted, keyed to that repository_id and discussion_id

  Scenario: OPENAI_API_KEY absent — feature entirely hidden, no hard failure
    Given OPENAI_API_KEY is not set
    When commits are analyzed and discussions are summarized
    Then no embedding API call is made
    And no embeddings are stored
    And the search_similar_commits tool is not offered to the LLM in the Ask tab
    And ingestion, analysis, and every other Ask-tab tool work exactly as before

  Scenario: Semantic search returns evidence-linked results
    Given a repository has stored embeddings for at least one CommitAnalysis and one
      DiscussionEvidence
    When search_similar_commits is called with a natural-language query
    Then the top-K results are ranked by cosine similarity to the query's embedding
    And each result includes its source type (commit_analysis or discussion_evidence), its
      evidence reference (commit_sha or discussion_url), and the summary text that was matched

  Scenario: Embedding API failure for a single item does not abort the batch
    Given the embedding API call fails for one commit's summary (timeout, rate limit,
      malformed response)
    When the rest of the analysis batch continues
    Then that one commit has no stored embedding
    And every other commit's embedding is computed and stored normally
    And the failure is logged with only its exception type name, never response bodies

  Scenario: Empty corpus returns an empty result, not an error
    Given a repository has zero stored embeddings (never analyzed, or OPENAI_API_KEY was
      absent throughout ingestion)
    When search_similar_commits is called
    Then it returns an empty list
    And no exception is raised

  Scenario: Raw untrusted text is never embedded
    Given a commit's raw diff/message and a discussion's raw title/body/answer text
    When embeddings are computed for that commit's CommitAnalysis and that discussion's
      DiscussionEvidence
    Then only the validated summary field(s) are ever passed to the embedding API
    And no raw commit message, diff content, or raw Discussion field ever reaches the
      embedding call

  Scenario: A malformed/empty query is rejected, not silently emptied
    Given search_similar_commits is called with an empty or whitespace-only query string
    When the tool executes
    Then it returns a clear validation error to the caller rather than an empty result set
      (distinguishing "bad input" from "no matches found")
```

---

## Domain concepts

- **`EmbeddedChunk`** (new frozen dataclass, `domain/embeddings.py`): the persisted,
  schema-validated embedding record. Fields: `repository_id: str`, `source_type: Literal[
  "commit_analysis", "discussion_evidence"]`, `source_id: str` (the `commit_sha` or
  `discussion_id` this embedding describes), `text: str` (the exact summary text that was
  embedded — kept for debugging/inspection, itself already-validated LLM output, never raw
  input), `vector: list[float]`, `model: str` (the embedding model name), `created_at: datetime`.
- **`EmbeddingClient`** (new `Protocol`, `application/ports.py`): `.embed(text: str) ->
  list[float]`. Mirrors the existing `LLMClient` protocol's minimalism.
- **`LiteLLMEmbeddingClient`** (new class, `infrastructure/llm.py`, alongside — not a
  modification of — `LiteLLMLLMClient`): wraps `litellm.embedding(model=..., input=[text])`,
  extracting the single embedding vector from the response. Requires `OPENAI_API_KEY` to be
  present in the environment for `litellm` to route the call; the composition layer is
  responsible for not constructing this client at all when the key is absent (see Failure modes).
- **`SqliteEmbeddingStore` / `PostgresEmbeddingStore`** (new stores, one row per
  `(repository_id, source_type, source_id)`, upserted): fit the existing split-package
  infrastructure layout — a new `embeddings.py` sub-module in both `infrastructure/sqlite/` and
  `infrastructure/postgres/`, re-exported from each package's `__init__.py`. The vector is
  stored as a JSON-encoded `TEXT`/`VARCHAR` column (`vector_json`) — deliberately not a
  Postgres-specific `vector` column type, so both backends use the identical schema and the
  identical in-process similarity-scan code path.
- **`EmbeddingService`** (new application-layer service, `application/embedding_service.py`):
  `embed_commit_analysis(repository_id, analysis: CommitAnalysis) -> EmbeddedChunk | None` /
  `embed_discussion_evidence(repository_id, evidence: DiscussionEvidence) -> EmbeddedChunk |
  None`, given an `EmbeddingClient`. Returns `None` (rather than raising) on any embedding-call
  failure, isolating that single item's failure from the surrounding batch — mirrors
  `DiscussionSummarizer`'s per-item isolation.
- **`SemanticSearchService`** (new application-layer service,
  `application/semantic_search_service.py`): `.search(repository_id: str, query: str, top_k: int
  = 10) -> list[SimilarityResult]`. Embeds the query via the same `EmbeddingClient`, loads every
  stored `EmbeddedChunk` for the repository via the embedding store, computes cosine similarity
  in Python between the query vector and every stored vector, returns the top-`k` sorted
  descending by score. `SimilarityResult` (new frozen dataclass, same module): `source_type,
  source_id, evidence_ref (commit_sha or discussion_url), summary_text, score: float`.
- **`build_embedding_client()`** (new factory, `composition.py`): returns
  `LiteLLMEmbeddingClient` when `OPENAI_API_KEY` is set, else `None`. Every call site that would
  use it (analysis pipeline, discussion summarization, the new tool's registration) must check
  for `None` and skip/hide accordingly — this is the single source of truth for "is the feature
  available."
- **`build_embedding_store()`** (new factory, `composition.py`): backend-aware, mirrors
  `build_discussion_evidence_store`.
- **Tool registration (locked)**: `search_similar_commits` is added to `tools/registry.py`'s
  tool set, but the *dispatch table* GitItGPT builds per-request (`chat/service.py`) only
  includes it when `build_embedding_client()` is non-`None` for that process — matching how
  other optional, credential-gated capabilities are already surfaced/hidden elsewhere in this
  codebase.
- **Embedding-computation trigger points (locked)**:
  - Commit analysis: inside `commit_analysis_service.py`, immediately after a `CommitAnalysis`
    is produced and validated, before/alongside its persistence — best-effort, never blocks
    analysis of that commit or the batch.
  - Discussion evidence: inside the discussion-summarization flow
    (`application/discussion_summarizer.py` output, persisted via the existing
    `_fetch_and_store_discussion_evidence` trigger point in `api/routes/repos.py`) — best-effort,
    same posture.

---

## Inputs and outputs

New public interfaces (signatures define the contract a future build batch must satisfy):

- `EmbeddedChunk(repository_id, source_type, source_id, text, vector, model, created_at)`
  (`domain/embeddings.py`, frozen dataclass)
- `EmbeddingClient.embed(text: str) -> list[float]` (`application/ports.py`, `Protocol`)
- `LiteLLMEmbeddingClient(model: str).embed(text: str) -> list[float]` (`infrastructure/llm.py`)
- `SqliteEmbeddingStore(database_path)` / `PostgresEmbeddingStore(conninfo)` —
  `.initialize()` / `.save_embeddings(repository_id, items: list[EmbeddedChunk])` (upsert) /
  `.get_all_embeddings(repository_id) -> list[EmbeddedChunk]`
  (`infrastructure/sqlite/embeddings.py`, `infrastructure/postgres/embeddings.py`)
- `EmbeddingService(embedding_client: EmbeddingClient).embed_commit_analysis(repository_id, analysis)
  -> EmbeddedChunk | None` / `.embed_discussion_evidence(repository_id, evidence) -> EmbeddedChunk
  | None` (`application/embedding_service.py`)
- `SimilarityResult(source_type, source_id, evidence_ref, summary_text, score)`
  (`application/semantic_search_service.py`, frozen dataclass)
- `SemanticSearchService(embedding_client, embedding_reader).search(repository_id, query,
  top_k=10) -> list[SimilarityResult]` (`application/semantic_search_service.py`)
- `build_embedding_client() -> LiteLLMEmbeddingClient | None` / `build_embedding_store(*,
  project_root) -> SqliteEmbeddingStore | PostgresEmbeddingStore` (`composition.py`)
- New tool `search_similar_commits(query: str, top_k: int = 10) -> list[dict]` in
  `tools/registry.py`, each result dict exposing only `source_type`, `evidence_ref`,
  `summary_text`, `score` — never raw commit/discussion content beyond what `CommitAnalysis`/
  `DiscussionEvidence` already exposed elsewhere.

---

## Evidence requirements

- Every `SimilarityResult` carries `evidence_ref` (a `commit_sha` or `discussion_url`) —
  identical evidence-citation discipline to every other Git It claim (CODEX.md,
  `EvidenceRef.commit_sha` for commit analyses, `DiscussionEvidence.discussion_url` for
  discussions).
- The chat `SYSTEM_PROMPT` (`chat/service.py`) must be extended with one instruction sentence:
  a claim built from a `search_similar_commits` result must cite the exact `evidence_ref` given
  for that result, following the same pattern already used for the existing four tools' outputs.
- `score` (cosine similarity) is surfaced to the LLM so it can judge relevance and avoid citing a
  low-relevance match as strong evidence — consistent with CODEX.md's "preserve uncertainty"
  principle.

---

## Failure modes

| Failure | Expected behavior |
|---|---|
| `OPENAI_API_KEY` unset | `build_embedding_client()` returns `None`; no embedding calls anywhere; `search_similar_commits` not registered; ingestion/analysis/chat otherwise unaffected. |
| Embedding API HTTP error, network error, timeout, rate limit | That single item's embedding is skipped (`EmbeddingService` returns `None`); logged at WARNING with `type(exc).__name__` only; the surrounding analysis/summarization batch continues normally. |
| Malformed/unexpected embedding API response shape | Treated as an embedding failure for that item → `None`, same as above. |
| `search_similar_commits` called with empty/whitespace query | Tool returns a validation error (distinct from "no matches"), not a silently empty result. |
| Repository has zero stored embeddings | `search_similar_commits` returns `[]`, no error — same accepted gap as un-re-analyzed pre-feature repositories. |
| Vector-store table does not exist yet (fresh SQLite workspace) | `initialize()` creates it on first use, mirroring every other store in this codebase. |
| Repository re-analyzed with new commits | New commits get new embeddings on their own analysis pass; existing embeddings for already-analyzed commits are untouched (no bulk re-embedding job). |

---

## Security considerations

- **A new third-party recipient of repository-derived text.** OpenAI's embedding API becomes a
  second external LLM-adjacent service (distinct from whichever provider backs primary
  analysis/narrative/chat completions) that receives Git It-derived text: the *already
  LLM-summarized* `CommitAnalysis`/`DiscussionEvidence` text (not raw commit/discussion content),
  plus — critically — the Ask-tab **user's own question text**, sent to OpenAI for query
  embedding. This second data flow (a live user's question, not just repository content) is new
  and should be called out explicitly wherever this feature is documented for end users.
- **The untrusted-input boundary is unchanged, just extended to a new destination.** Only
  already-validated `CommitAnalysis.summary`/`summary_beginner`/`summary_expert` and
  `DiscussionEvidence.summary` are ever embedded — never a raw commit message, diff, or raw
  `Discussion` field. This is the same boundary ADR 008/015 already established; this spec
  extends it to cover "embedding API input" the same way it already covers "narrative-prompt
  input."
- **No secret leakage.** `OPENAI_API_KEY` is never logged, matching the existing convention for
  `GITHUB_TOKEN`/`ANTHROPIC_API_KEY` (only `type(exc).__name__` is logged on failure).
- **Embedding vectors are opaque numeric data**, not free text — there is no injection surface
  on the *return* path from the embedding API (a list of floats cannot carry a prompt-injection
  payload the way a text response could).

---

## Privacy considerations

- Commit/discussion summaries are already public GitHub-derived content (same assumption already
  accepted for narrative generation) — sending them to a second third party (OpenAI, for
  embedding) does not introduce a new class of *repository* data exposure, but does introduce a
  *new recipient* of that data, worth disclosing.
- The end user's own Ask-tab question text is sent to OpenAI for query embedding — this is a new
  category of data flow (a live person's input, not repository content) introduced by this
  feature specifically, and should be flagged in any user-facing privacy documentation.
- No discussion participant identity or commit author identity is embedded or exposed by this
  feature beyond what `CommitAnalysis`/`DiscussionEvidence` already expose elsewhere.

---

## Observability

Every embedding API call and every `search_similar_commits` invocation must emit a structured
log record via the shared mechanism defined in spec 024 (`call_site="embedding"` /
`call_site="semantic_search"`), metadata only — no summary text, no query text, no vector
contents in the log. Until spec 024 ships, a minimal interim posture is acceptable: `_logger.debug`
on skip (`OPENAI_API_KEY` absent), `_logger.warning` on embedding failure (`type(exc).__name__`
only), `_logger.info`/`debug` after a batch completes with counts only (items embedded, items
skipped/failed) — mirroring the observability posture already established in spec 022.

---

## Tests required

### Unit tests (new — a future build batch must write these, TDD, failing first)

- `tests/unit/test_embeddings_domain.py`: `EmbeddedChunk` construction/shape.
- `tests/unit/test_embedding_service.py`: successful embed produces an `EmbeddedChunk` with the
  correct `source_type`/`source_id`/text; embedding-client failure returns `None` without
  raising; only `CommitAnalysis.summary`-family / `DiscussionEvidence.summary` text is ever
  passed to the embedding client (assert on the exact string passed, proving no raw
  commit/discussion field ever reaches it).
- `tests/unit/test_embedding_store_sqlite.py`: insert + read roundtrip; upsert overwrites the
  same `(repository_id, source_type, source_id)`; unknown repository returns `[]`; distinct
  repositories independent; `initialize()` idempotent — mirroring
  `test_discussion_evidence_store_sqlite.py`'s structure.
- `tests/unit/test_postgres_adapters.py` (extended): `PostgresEmbeddingStore` roundtrip + upsert,
  gated by the existing `DATABASE_URL`-must-start-with-`postgresql` skip marker.
- `tests/unit/test_semantic_search_service.py`: given a fixed set of stored vectors and a query
  vector, results are ranked by cosine similarity descending, truncated to `top_k`; empty corpus
  returns `[]`; each result carries the correct `evidence_ref` for its source type; empty/
  whitespace query raises a validation error rather than returning `[]`.
- `tests/unit/test_chat_tools_semantic_search.py` (or extending the existing chat/tools test
  file): `search_similar_commits` is present in the dispatch table when `build_embedding_client()`
  is non-`None`, and absent when it is `None`; a successful call's result shape exposes only
  `source_type`/`evidence_ref`/`summary_text`/`score` fields.
- A schema-level test asserting the embedding call site never receives text containing any
  sentinel value planted only in a raw `Discussion`/commit-message fixture (the deterministic,
  unit-testable form of the "no raw text leakage" requirement, mirroring spec 022's equivalent
  eval-level check but as a fast unit test here).

### TDD order

Red → Green → Refactor per module, in dependency order: domain (`EmbeddedChunk`) → stores
(SQLite → Postgres) → `EmbeddingService` → `SemanticSearchService` → composition wiring → tool
registration/chat integration — matching the layering already used for spec 022's rollout.

---

## Evaluation required

A new eval (`evals/semantic_search_eval.py`, mirroring `evals/discussion_evidence_eval.py`'s
structure), gated on `OPENAI_API_KEY` (skips cleanly with exit 0 if absent, same posture as
`evals/run.py`):

1. **Concept-recall check**: a fixture set of `CommitAnalysis` summaries covering several
   distinct, clearly-separated concepts (e.g. "SQL injection fix," "flaky test suite," "database
   migration rollback") plus a matching set of natural-language queries that describe each
   concept using *different words* than the summaries themselves use. Assert that for each
   query, the known-correct commit(s) appear within the top-`k` results.
2. **No raw-text leakage in results**: none of the fixture's raw (hypothetical) commit-message
   text appears in any `SimilarityResult.summary_text` — only the validated summary is ever
   surfaced (deterministic check, mirrors spec 022's eval).
3. **Relevance ordering sanity**: a query closely matching one summary's wording should score
   higher than a query about an unrelated concept, over the same fixture set — a coarse sanity
   check on the embedding model's usefulness for this corpus, not a strict correctness proof.

---

## Documentation impact

- A future build batch creates `docs/progress/{area}/batch-{N}-semantic-search.md` (area:
  likely `analysis` or `api`, decided at build time).
- `docs/progress/README.md` gets a new entry.
- `docs/prompt-contracts/gitit-gpt-system-prompt.md` (or equivalent) gets the new
  evidence-citation instruction sentence documented, mirroring how spec 022 updated
  `docs/prompt-contracts/narrative-generation.md`.
- No documentation impact from *this* batch beyond the spec itself — no production code changes
  ship here.

---

## ADR impact

**Assessment: a new ADR is warranted**, for two reasons that cross the threshold used elsewhere
in this repo:

1. This introduces the project's **first embedding-based retrieval mechanism** — a genuinely new
   architectural capability, and a deliberate **divergence from ADR 006's original plan**
   (PostgreSQL + pgvector). ADR 006 explicitly defers pgvector as future work; this spec solves
   the retrieval need a different way (in-process, backend-agnostic cosine similarity) rather
   than acting on that deferred plan. The ADR should record *why*: pgvector would make the
   feature Postgres-only, contradicting the project's local-first, SQLite-default posture (ADR
   005/010), whereas in-process search works identically on both backends at this project's
   realistic scale.
2. This introduces a **second external LLM-adjacent API dependency** (OpenAI, for embeddings)
   alongside whatever primary provider serves completions — a genuinely new external-dependency
   and credential-management decision, distinct from anything ADR 007 (local git mining + GitHub
   MCP/API) or the existing LiteLLM-based completions already cover.

A follow-up ADR should be authored alongside (or just before) the implementation build batch.

---

## Open questions

1. **Exact embedding model name and dimensionality.** Proposed default: OpenAI's
   `text-embedding-3-small` (low cost, ample dimensionality for short one-paragraph summaries),
   as a configurable constant (env-var-backed, following the batch-74 convention) — not locked;
   should be confirmed/tuned during implementation against real cost and the evaluation's
   concept-recall results.
2. **Default `top_k`.** Proposed default: 10, configurable per call — not locked; may need
   tuning once the evaluation harness (see Evaluation required) is run against a realistic
   fixture.
3. **Re-embedding on re-analysis.** If a `CommitAnalysis` is regenerated (e.g. re-analyzed with a
   different model), should its embedding be recomputed? Proposed: yes, via the same
   `(repository_id, source_type, source_id)` upsert already used for storage — but this is an
   assumption, not a locked decision, and should be confirmed during implementation.
4. **Cost estimation surfacing.** Should the existing `/analyze/estimate` cost-estimate endpoint
   (`api/cost.py`, batch 74/69) be extended to include a per-commit embedding cost line item,
   given a new paid API call is now made per analyzed commit? Not addressed by this spec; flagged
   for the implementation batch to decide.

---

## Out of scope

- Implementation of any kind (domain model, stores, services, tool registration, chat wiring,
  tests, evals) — deferred to a future build batch.
- The follow-up ADR referenced above.
- pgvector, any external vector-database service, or chunking of long text.
- A REST endpoint or frontend UI for directly browsing embeddings or similarity scores.
- Backfilling embeddings for repositories analyzed before this feature ships.
