## Batch 117 — Wire observe_llm_call into all 5 LLM call sites (spec 024, slice 2)

### Goal

Apply the `observe_llm_call` decorator built in batch 116 to the five real LLM
call sites identified in spec 024, resolving the spec's two open questions
along the way: how `LiteLLMLLMClient`'s dual-purpose reuse gets the correct
`call_site`, and how a streaming generator call site (`respond_stream`) can be
observed without only measuring generator-creation time.

### Why

Batch 116 built and fully tested the observability mechanism in isolation
against a fake wrapped function, per spec 024's locked TDD order. This batch
applies it to production code with no change to any call site's prompts,
models, or business logic — a pure cross-cutting addition.

### What was added

**`infrastructure/observability.py`**
- `observe_llm_call`'s `call_site` parameter is now `CallSite = str |
  Callable[[Any], str]` instead of a fixed `str`. When callable, it is invoked
  with the wrapped method's own instance (`self`) at call time to resolve the
  actual call site — added specifically to solve spec 024's open question #2
  below. A plain string still works exactly as before (all four non-dual
  call sites use a fixed string).
- `observe_llm_call_stream(call_site: str)` — a new, generator-aware sibling
  decorator for streaming call sites. Unlike `observe_llm_call`, the wrapper
  itself is a generator function: it starts timing only once the caller
  begins iterating (matching the underlying call's own laziness — no
  observation fires merely from calling the decorated method), delegates the
  full iteration via `yield from` inside a `try/except`, and builds+emits the
  observation exactly once — after the stream is fully exhausted (`else`
  branch) or when it raises during iteration (`except` branch, `success=False`,
  `error_type=type(exc).__name__`, exception re-raised unchanged). If the
  caller abandons the stream early without an exception (e.g. `next()` once
  and never resumes), no observation is emitted — there's no well-defined
  duration/outcome for a stream that was neither finished nor failed.

**`infrastructure/llm.py`**
- `InstructorCommitAnalysisAdapter.analyze_commit` → `@observe_llm_call
  ("commit_analysis")`.
- `InstructorPatternSynthesisAdapter.synthesize` → `@observe_llm_call
  ("pattern_synthesis")`.
- `LiteLLMLLMClient.__init__` gained a new `call_site: str =
  "narrative_generation"` constructor parameter, stored as `self._call_site`.
  `LiteLLMLLMClient.complete` is decorated with `@observe_llm_call(lambda
  self: self._call_site)` — the callable form resolves the correct call site
  per-instance at call time.

**`chat/litellm_client.py`**
- `LiteLLMChatClient.respond` → `@observe_llm_call("chat")` (plain
  synchronous method, straightforward).
- `LiteLLMChatClient.respond_stream` → `@observe_llm_call_stream("chat")`
  (generator function using `yield`; needed the new generator-aware
  decorator, not the plain one).

**`composition.py`**
- `build_discussion_summarizer` now constructs `LiteLLMLLMClient(model=model,
  call_site="discussion_summarization")`.
- `build_narrative_service` (both the PostgreSQL and SQLite branches) now
  constructs `LiteLLMLLMClient(model=_NARRATIVE_MODEL,
  max_tokens=_NARRATIVE_MAX_TOKENS, call_site="narrative_generation")` —
  explicit even though it matches the constructor default, so the wiring is
  visible at the call site rather than relying on an implicit default.

### Resolving spec 024's open question #2 (call-site ownership for `LiteLLMLLMClient`)

Chose: **constructor parameter + a callable `call_site` argument to
`observe_llm_call`**, over the alternative of not decorating `.complete()` at
class-definition time and instead having it call an internal helper manually.
This keeps `observe_llm_call`'s existing single decorator-based API uniform
across all four non-streaming call sites (three take a fixed string, one
takes a callable) rather than introducing a second, bespoke observation path
just for this one class. The generalization is small (one `_resolve_call_site`
helper, one type alias) and immediately reusable if a future call site needs
the same per-instance resolution.

### Resolving the streaming timing-correctness gap (`respond_stream`)

`observe_llm_call` applied directly to a generator function would only time
generator *creation* (near-instant, since `respond_stream`'s body doesn't run
until first iterated) and would report `success=True` even if `litellm`'s
underlying stream iterator raises partway through — because the decorator's
`try/except` would have already returned by the time the real error surfaces
during later iteration. `observe_llm_call_stream` closes this by making the
wrapper itself a generator: the `try/except .../else` sits around a `yield
from`, so timing and success/failure are measured across the *entire*
consumption, not just the call that hands back the generator object.

### Tests added

- `tests/unit/test_observability.py` (+1): `observe_llm_call` resolves a
  callable `call_site` per-instance — two instances of the same class with
  different `_call_site` values each emit the correct value.
- `tests/unit/test_observability_stream.py` (new, 5 tests): generator
  creation alone emits nothing until consumed; successful full consumption
  emits one `success=True` record; duration reflects the full stream
  (asserted via a slow fake generator with `time.sleep` between yields, not
  generator-creation time); an exception raised mid-iteration emits
  `success=False`/correct `error_type` and still re-raises; abandoning a
  stream early (partial consumption, no exception) emits no observation.
- `tests/unit/test_llm_infrastructure_observability.py` (new, 4 tests):
  `InstructorCommitAnalysisAdapter.analyze_commit` observed with
  `call_site="commit_analysis"`; `InstructorPatternSynthesisAdapter.synthesize`
  observed with `call_site="pattern_synthesis"`; `LiteLLMLLMClient.complete`
  defaults to `call_site="narrative_generation"`; constructing it with
  `call_site="discussion_summarization"` emits that value instead.
  `instructor.from_litellm` and `litellm.completion` are monkeypatched — no
  real API calls, mirroring `test_litellm_chat_client.py`'s existing pattern.
- `tests/unit/test_litellm_chat_client.py` (+3): `respond` observed with
  `call_site="chat"`; `respond_stream` emits no observation until the full
  stream is consumed, then emits `success=True`; a provider generator that
  raises mid-stream (`RuntimeError` after one chunk) produces a
  `success=False` observation with `error_type="RuntimeError"` and the
  exception still propagates through the caller's iteration.
- `tests/unit/test_repository_ingestion_composition.py` (+2):
  `build_narrative_service` wires `LiteLLMLLMClient._call_site ==
  "narrative_generation"`; `build_discussion_summarizer` wires
  `LiteLLMLLMClient._call_site == "discussion_summarization"`.

Full suite: **900 passed, 21 skipped** (was 885 passed / 21 skipped before
this batch; +15 new passing tests, no regressions).

### Gotchas

- Ruff's `UP028` flagged the initial `for item in func(...): yield item` /
  `except .../else` shape in `observe_llm_call_stream` and equivalent
  patterns in the new test fakes — replaced with `yield from` throughout.
  `yield from` fully delegates exceptions raised during the delegate's
  iteration, so this is behavior-preserving, not just a style fix.
- The existing ad hoc `_logger.debug` start/end logging inside
  `InstructorCommitAnalysisAdapter.analyze_commit` was left in place
  unchanged — spec 024 adds a new structured observability record alongside
  it, it does not replace or remove any existing logging.
- `build_narrative_service`'s two backend branches (PostgreSQL, SQLite) both
  needed the same `call_site="narrative_generation"` change — easy to update
  only one and silently leave the other on the constructor default (which
  happens to be correct today, but would silently drift if the default ever
  changed for an unrelated reason).

### Commits

- `feat: wire observe_llm_call into all 5 LLM call sites (spec 024)`
