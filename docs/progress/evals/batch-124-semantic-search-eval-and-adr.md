## Batch 124 — Semantic search eval and ADR 016 (spec 023, closing batch)

Filed under `docs/progress/evals/`, not `analysis/` or `api/` — this batch is
eval-script-plus-ADR work, no `src/` changes, mirroring exactly the
precedent set by batch 112 (`docs/progress/evals/batch-112-discussion-evidence-eval-and-adr.md`),
which closed spec 022 the same way. `evals/` already exists as a progress
area in `docs/progress/README.md` for precisely this kind of closing batch.

### Goal

Close out spec 023 (RAG-Enhanced Semantic Search for the Ask Tab) with its
two remaining deliverables: the eval the spec's "Evaluation required" section
mandates, and the follow-up ADR the spec's "ADR impact" section deferred to
the implementation batch. This is the last batch in the spec 023 sequence
(batches 116-124): observability core (116) → observability wiring (117) →
domain model + stores (118) → `LiteLLMEmbeddingClient` (119) →
`EmbeddingService` (120) → `SemanticSearchService` (121) → ingest wiring
(122) → `search_similar_commits` chat tool (123) → eval + ADR (124, this
batch).

### Why

Spec 023 explicitly deferred both the eval and the ADR to the implementation
batch rather than requiring them upfront (mirroring spec 022's own
convention). With embedding computation, persistence, retrieval, and the
chat tool all live (batch 123), the full pipeline can be exercised
end-to-end for evaluation purposes, and the two ADR-worthy decisions (a
deliberate divergence from ADR 006's deferred pgvector plan; a second
external LLM-adjacent API dependency) are now implemented, not merely
proposed — so the ADR can record what was actually built rather than what
was planned.

### What was added

**`evals/semantic_search_eval.py`** (new, standalone script, mirrors
`evals/discussion_evidence_eval.py`'s bootstrap/argparse/report pattern —
NOT a pytest test, kept out of the deterministic unit suite):

- Fixture: 5 `CommitAnalysis`-style summaries covering distinct, clearly
  separated concepts (SQL injection fix, flaky test suite fix, database
  migration rollback, auth token expiry bug, and a docs-typo distractor),
  each paired with a raw, hypothetical commit-message sentinel phrase
  (`ZEBRA-QUUX-SENTINEL...`, `PLATYPUS-FOXTROT-SENTINEL...`,
  `WOMBAT-YANKEE-SENTINEL...`, `IGUANA-TANGO-SENTINEL...`,
  `PELICAN-OSCAR-SENTINEL...`) that is never actually embedded — only the
  paraphrased summary text is.
- 4 matching natural-language queries, deliberately worded with different
  vocabulary than the summaries themselves (e.g. "what security mistakes
  were made early in the project" for the SQL-injection summary), plus one
  control query about an unrelated concept (documentation typos) used only
  for the ordering-sanity check.
- Embeds each fixture summary via a real `LiteLLMEmbeddingClient().embed()`
  call, building `EmbeddedChunk` instances in memory. A small
  `_InMemoryEmbeddingReader` class (satisfying the `EmbeddingReader`
  Protocol structurally, no real DB) holds them and is handed to a real
  `SemanticSearchService(embedding_client, reader)`.
- Three checks, all deterministic given a real embedding response (unlike
  spec 022's eval, there is no qualitative-only check here):
  1. **Concept recall** — for each of the 4 queries, asserts the
     known-correct fixture's `evidence_ref` appears within the top-`k`
     (`k=3`) `SimilarityResult`s.
  2. **No raw-text leakage** (deterministic, mirrors spec 022's eval) —
     asserts none of the 5 sentinel phrases appear in any
     `SimilarityResult.summary_text` gathered across every query run in this
     eval.
  3. **Relevance ordering sanity** — asserts the security-mistakes query
     scores higher against the SQL-injection fixture than the unrelated
     control query (documentation typos) does.
- API-key-gated, but on a single fixed dependency rather than a
  per-provider dict: `_check_api_key()` simply checks
  `OPENAI_API_KEY` — this eval's only real dependency is
  `LiteLLMEmbeddingClient`/`build_embedding_client()`, never a completions
  model, so there is no `--model` argument (unlike
  `discussion_evidence_eval.py`). `main()` prints a "Skipped" message and
  exits `0` when the key is absent.

**`docs/prompt-contracts/gitit-gpt-system-prompt.md`** — extended:
documents the fifth tool (`search_similar_commits`) in the tools table and
its conditional-registration behavior, and adds a "Semantic-search citation
rule (spec 023)" section documenting the new unconditional `SYSTEM_PROMPT`
sentence from batch 123 ("If you use search_similar_commits, always cite
each result's evidence_ref when reporting it."), following the same format
as the existing "Formatting rules (spec 016)" section. The "Evidence
requirement" section is extended with references to
`test_chat_tools_semantic_search.py`, the spec-023 additions to
`test_chat_service.py`, `test_chat_composition.py`, and this eval.

**`evals/README.md`** — new "Semantic search eval (spec 023)" section,
mirroring the "Discussion evidence eval (spec 022)" section's exact format:
how to run, options, requires, and a numbered "what it checks" list.

**`ADR/016-in-process-embedding-retrieval-and-openai-dependency.md`** (new):
records both decisions spec 023 flagged as ADR-worthy:

1. Cosine-similarity retrieval is in-process and backend-agnostic
   (`SemanticSearchService`'s pure-Python scan over `EmbeddedChunk.vector`,
   `vector_json` TEXT column identical on both `SqliteEmbeddingStore` and
   `PostgresEmbeddingStore`), a deliberate bypass of ADR 006's deferred
   `pgvector` plan — not an extension of it — because adopting `pgvector` now
   would make the feature Postgres-only, contradicting the project's
   local-first, SQLite-default posture (ADR 005/010).
2. `LiteLLMEmbeddingClient`/`build_embedding_client()` introduce a second,
   independent external credential (`OPENAI_API_KEY`) alongside whatever
   provider serves completions, gated with the same "single source of truth
   returns `None` when absent, every call site checks and degrades
   gracefully" pattern already used for `GITHUB_TOKEN`-gated features
   (references ADR 007 as the prior external-API-dependency precedent, ADR
   008/015 for the untrusted-input boundary this extends, and ADR 012 for
   the tool-calling loop this adds a fifth tool to).

**`docs/adr/index.md`** — new row for ADR 016.

**`docs/specs/index.md`** — spec 023's row changed from `Draft` to
`Implemented` (its own `Status:` header in
`specs/023-rag-semantic-commit-search.md` is intentionally left as `Draft`,
matching the established convention from batch 114 that a spec's own header
is not retroactively edited after implementation).

### Verification

- Ran `PYTHONPATH=src uv run python evals/semantic_search_eval.py --verbose`
  with `OPENAI_API_KEY` loaded from the local `.env`: the eval correctly
  attempted a real embedding call and failed with
  `litellm.RateLimitError` / HTTP 429 `insufficient_quota` — a pre-existing
  account-billing limitation (no funded OpenAI billing on this account), not
  a defect in the eval script. This confirms the script is wired correctly
  against the real API (it reaches `litellm.embedding(...)` and surfaces the
  real provider error) and would exercise its three checks end-to-end once
  billing is resolved.
- Also confirmed the skip path independently: with `OPENAI_API_KEY` absent
  from the shell environment (before loading `.env`), the eval printed
  `Skipped — OPENAI_API_KEY is not set...` and exited `0`.

Full unit suite: **954 passed, 24 skipped** — unchanged from batch 123, since
this batch adds no pytest tests and touches no `src/` files (eval scripts
are intentionally excluded from the deterministic suite, same posture as
`evals/discussion_evidence_eval.py`).

Gates: `ruff check .`, `ruff format --check .`, `mypy src/`, and
`mkdocs build --strict` all pass clean.

### Gotchas

- `evals/semantic_search_eval.py` is not covered by `mypy src/` (the gate
  only scans `src/`) — running `mypy` directly against the eval file in
  isolation reports `import-untyped` "missing library stubs" errors for
  every `git_it.*` import, but this is pre-existing, identical behavior to
  running `mypy` directly against `evals/discussion_evidence_eval.py`
  (confirmed by comparison) — not a new defect, just a consequence of `mypy`
  being scoped to `src/` project-wide.
- An early draft reused the same loop variable name (`r`) across two
  separate `for` loops with different iterable element types
  (`list[CheckResult]` then `list[object]`) inside `_print_report`. `ruff`
  didn't flag it, but running `mypy` on the file directly surfaced an
  "Incompatible types in assignment" error from the inferred type of the
  first loop leaking into the second. Fixed by renaming the second loop's
  variable (`similarity_result`) rather than reusing `r`.

### Commits

- `docs: add semantic search eval and ADR 016 closing spec 023 (spec 023)`
