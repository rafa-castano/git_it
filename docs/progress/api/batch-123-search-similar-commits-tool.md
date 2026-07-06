## Batch 123 — Wire `search_similar_commits` RAG tool into GitItGPT chat (spec 023, slice 6)

### Goal

Wire spec 023's `SemanticSearchService` (batch 121) into the Ask-tab chat service as a sixth
tool call: `search_similar_commits`. Before this batch, embeddings were computed and persisted at
ingest time (batch 122) and retrievable via `SemanticSearchService.search`, but nothing let the
model actually call it — same "foundation built, nothing invokes it live" gap spec 023 calls out,
now closed for retrieval.

### Why

Closes the last gap between "embeddings exist" and "GitItGPT can ground an answer in them."
Registered conditionally (`include_semantic_search`), gated on `build_embedding_client() is not
None` (i.e. `OPENAI_API_KEY` set), so the tool is silently absent — not offered, not in the
dispatch table — when the RAG feature is unavailable, matching every other RAG call site's
gating convention (batch 118-122).

### What was added

**`src/git_it/tools/registry.py`**
- New `search_similar_commits(project_root, repository_id, query, top_k=DEFAULT_TOP_K) ->
  SimilaritySearchResponse` function, following the same self-contained style as the other four
  tool functions: builds its own dependencies from `project_root` rather than taking them as
  constructor-injected collaborators.
- Calls `build_embedding_client()` first; returns an empty `SimilaritySearchResponse` immediately
  if it's `None` (no `OPENAI_API_KEY`) without touching `build_embedding_store`.
- Otherwise builds `build_embedding_store(project_root=project_root)`, constructs
  `SemanticSearchService(embedding_client, embedding_store)`, and calls `.search(repository_id,
  query, top_k=top_k)` inside a `try/except ValueError` — `SemanticSearchService.search` raises
  `ValueError` for a blank query, which this function swallows into an empty response rather than
  propagating, consistent with this file's "never raises to the caller" contract.
- Maps each `SimilarityResult` (`source_type`, `evidence_ref`, `summary_text`, `score`) to a
  `SimilaritySearchResult` and wraps the list in `SimilaritySearchResponse`.
- Module-level names (`build_embedding_client`, `build_embedding_store`, `SemanticSearchService`)
  are referenced as bare names so test monkeypatching of `registry.<name>` works.

**`src/git_it/chat/service.py`**
- `ChatService.__init__` gains a new keyword-only parameter `include_semantic_search: bool =
  False`.
- The module-level `READ_ONLY_TOOLS` dict and `_tool_schemas()` function are unchanged (nothing
  else imports them directly) and now only seed two new **instance** attributes built in
  `__init__`: `self._tools: dict[str, Callable[..., Any]]` (copied from `READ_ONLY_TOOLS`) and
  `self._tool_schemas: list[dict[str, Any]]` (copied from `_tool_schemas()`). When
  `include_semantic_search` is `True`, `"search_similar_commits": registry.search_similar_commits`
  is added to `self._tools` and one more schema dict is appended to `self._tool_schemas` — read at
  construction time, so a test that monkeypatches `registry.search_similar_commits` before
  constructing `ChatService(..., include_semantic_search=True)` gets the patched callable in the
  dispatch table.
- `chat()`, `chat_stream()`, and `_dispatch()` now read `self._tool_schemas` / `self._tools`
  instead of the old module-level `_tool_schemas()` call / `READ_ONLY_TOOLS.get(...)` lookup. The
  default (`include_semantic_search` absent) is byte-for-byte identical to before this batch: the
  four existing tools, same schemas, same dispatch behavior.
- `SYSTEM_PROMPT` gained one unconditional sentence instructing the model to cite each
  `search_similar_commits` result's `evidence_ref` when reporting it. Unconditional is intentional
  — the instance-level system prompt isn't built per-service, and mentioning a tool that might not
  be offered in a given instance is harmless (the model simply never sees the tool schema when
  it's absent).

**`src/git_it/chat/composition.py`**
- `build_chat_service` now imports `build_embedding_client` from
  `git_it.repository_ingestion.composition`, computes `include_semantic_search =
  build_embedding_client() is not None`, and passes it into the `ChatService(...)` constructor
  call — the same single source of truth (`OPENAI_API_KEY` via `build_embedding_client`) already
  used by `build_commit_analysis_service` (batch 122) and the discussion-evidence ingest flow.

### Tests added

The three test files were written in a prior, interrupted session and were already present as
RED tests; this batch only added the production code to turn them GREEN (no test files were
modified):

- `tests/unit/test_chat_tools_semantic_search.py` (3 tests) — `search_similar_commits` returns
  ranked results via a stubbed `SemanticSearchService`, returns empty when
  `build_embedding_client()` is `None`, and returns empty (not raising) for a blank query that
  makes the service raise `ValueError`.
- `tests/unit/test_chat_service.py` (+3, appended to the existing file) — the default
  `ChatService(...)` construction still offers/dispatches exactly the four existing tools;
  `include_semantic_search=True` offers and dispatches the fifth tool, including proving the
  dispatch table respects a `registry.search_similar_commits` monkeypatch performed before
  construction; `SYSTEM_PROMPT` (lowercased) contains both `"evidence_ref"` and
  `"search_similar_commits"`.
- `tests/unit/test_chat_composition.py` (2 tests, new file) — `build_chat_service` enables
  `search_similar_commits` when `OPENAI_API_KEY` is set and omits it when unset.

Full suite: **954 passed, 24 skipped** (24 skips pre-date this batch — unrelated optional-
dependency skips, not new). Ran the complete suite since this touches the shared `ChatService`
dispatch loop used by all four existing production tools.

Gates: `ruff check .`, `ruff format --check .`, `mypy src/` all pass clean for the three
production files this batch touched
(`src/git_it/tools/registry.py`, `src/git_it/chat/service.py`, `src/git_it/chat/composition.py`).
`ruff check .`/`ruff format --check .` flag two pre-existing, non-functional nits inside the
already-written test files from the interrupted prior session (an unsorted import block in
`tests/unit/test_chat_service.py`, a formatting diff in
`tests/unit/test_chat_tools_semantic_search.py`) — left untouched per this batch's explicit
constraint not to modify any of the three test files; they don't affect test correctness (all 19
tests across the three files pass) and are candidates for a follow-up mechanical formatting-only
commit if desired.

### Gotchas

- `SemanticSearchService.search` raises `ValueError` (not returning an empty list) for a blank
  query — `search_similar_commits` must catch that specifically, not just check `query.strip()`
  itself, so the exact validation logic stays in one place (the service).
- The dispatch-table entry for `search_similar_commits` must be read from `registry.<name>` at
  `ChatService.__init__` time (not through a `from ... import search_similar_commits` at module
  load time in `service.py`) so tests can monkeypatch `registry.search_similar_commits` on the
  module object before constructing the service and have the dispatch table pick up the patched
  callable.

### Commits

- `feat: wire search_similar_commits RAG tool into GitItGPT chat (spec 023)`
