## Batch 109 — Discussion summarizer with injection-safe URL boundary (spec 022, slice 3)

### Goal

Implement `DiscussionSummarizer`, the application-layer service that turns each qualifying
`Discussion` (raw, ephemeral, fetched by the batch-108 GraphQL fetcher) into a single
schema-validated `DiscussionEvidence` item, one LLM call per discussion. This is slice 3 of
spec 022's build order (fetcher → summarizer → narrative → wiring); the narrative
integration and ingest-time wiring land in later batches.

### Why

The fetcher (batch 108) produces raw `Discussion` candidates; nothing yet turns them into
narrative-safe evidence. `DiscussionSummarizer` is the second LLM call site in Git It whose
sole input is untrusted, external, community-authored text (the first is the per-commit
PR/issue enrichment in `commit_analysis_service`) — so it carries the same untrusted-data
security posture as `narrative_service._BASE_PROMPT`, scoped to a single discussion.

### What was added

**`application/discussion_summarizer.py`** (new)
- `DiscussionSummarizer(llm_client: LLMClient, *, model: str)` — `model` is injected by
  composition, keeping the application layer free of infrastructure imports (no
  `DEFAULT_MODEL` import here).
- `summarize(discussions: list[Discussion]) -> list[DiscussionEvidence]` — exactly one
  `llm_client.complete()` call per discussion; system prompt carries an untrusted-data
  security preamble equivalent to `narrative_service._BASE_PROMPT`'s, scoped to summarizing
  the single discussion, instructing the model to return only a JSON object with
  `claim_type`, `summary`, `confidence`, `limitations`.
- User message wraps the discussion's raw fields (title, body, answer_body, category) in a
  `[DISCUSSION DATA] ... [/DISCUSSION DATA]` untrusted-data envelope.
- Response parsing is defensive: strip whitespace and markdown code fences
  (` ```json ... ``` `), `json.loads`, then read only the four semantic keys.
- Per-item failure isolation: `complete()`, parsing, and construction are wrapped in
  try/except catching `(json.JSONDecodeError, ValidationError, KeyError, TypeError,
  ValueError)` plus a broad `except Exception` around the whole block (so `complete()`
  itself raising anything cannot abort the batch). On failure, logs
  `_logger.warning("discussion summarization failed: %s", type(exc).__name__)` and drops
  that one discussion — never the discussion content or the raw exception text.
- Logs input/summarized/dropped counts once at the end via `_logger.info` — no discussion
  content in any log line.

### Tests added

`tests/unit/test_discussion_summarizer.py` (12 tests), using a stub `LLMClient` with
scripted per-call responses:
- valid JSON response → validated `DiscussionEvidence` with `claim_type`/`summary`/
  `confidence`/`limitations` from the LLM;
- **URL trust-boundary test**: LLM JSON also contains a bogus `discussion_url` — asserts the
  resulting `DiscussionEvidence.discussion_url` is the trusted `Discussion.url`, not the
  LLM's value;
- missing `claim_type`/`summary`/`confidence` → dropped;
- `confidence` outside `[0.0, 1.0]` → dropped (schema rejects it);
- non-JSON response → dropped;
- response wrapped in a markdown code fence → still parsed;
- one discussion's `complete()` raising in a batch of three → that one dropped, the other
  two still summarized, in input order;
- exactly one `complete()` call per discussion (call-count assertion);
- system prompt contains the security preamble (`"disregard it"` substring);
- empty input list → empty output, zero LLM calls.

Full suite: **858 passed, 21 skipped** (was 846 passed / 21 skipped before this batch; +12
new tests, all in `test_discussion_summarizer.py`).

### Gotchas

- **URL/id trust-boundary reconciliation** (documented per CODEX.md's security-outranks-AC
  conflict order in AGENTS.md): the acceptance criteria in spec 022 ("Evidence-link
  requirement") reads as though the LLM's `discussion_url` is validated by the
  `DiscussionEvidence` schema and dropped if malformed — implying the LLM is the source of
  the URL. The Security considerations section states a stronger, more specific control:
  `discussion_id`/`discussion_url` must come from the trusted `Discussion` object, never the
  LLM's JSON output, because a successfully prompt-injected LLM response could otherwise
  turn the citation link into an attacker-controlled URL. This batch implements the
  Security-section version — the LLM's JSON is only ever consulted for `claim_type`,
  `summary`, `confidence`, `limitations`; `discussion_id`/`discussion_url`/`source_inputs`
  are always constructed from the trusted `Discussion` — and the schema-level URL regex
  validation in `DiscussionEvidence` (already tested in `test_discussions_domain.py`) is kept
  as defense-in-depth, not the primary control. AGENTS.md's conflict-resolution order ranks
  security constraints above explicit specification/AC wording, so this is the correct
  precedence, not a spec violation.
- mypy needed an explicit `dict[str, Any]` return type (with a `# type: ignore[no-any-return]`
  on the `json.loads` result) for `_parse_payload` — without it, `object`-typed dict values
  didn't satisfy `DiscussionEvidence`'s concrete field types (`Literal[...]`, `str`, `float`,
  `list[str]`) at the constructor call site.
- The broad `except Exception` around the LLM call is intentional and scoped tightly to
  `_summarize_one`: the whole point of per-item isolation is that a misbehaving `complete()`
  implementation (network error, provider outage, unexpected exception type) must not abort
  summarization of the remaining discussions in the batch.

### Commits

- `feat: add discussion summarizer with injection-safe URL boundary (spec 022)`
