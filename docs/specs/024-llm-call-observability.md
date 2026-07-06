# Feature Spec: LLM Call Observability (Structured Logging)

**Status:** Draft
**Spec number:** 024
**Author:** Rafael Castaño
**Date:** 2026-07-05

---

## Summary

Introduce one shared, structured-logging seam that every LLM (and, once spec 023 ships,
embedding) call site in Git It routes through, emitting exactly one JSON-structured log record
per call: model, call site, duration, success/failure, token counts (best-effort), estimated
cost, and repository context — **metadata only, never prompt or response content**. This
replaces today's inconsistent, mostly-absent ad hoc logging across the five existing LLM call
sites with one consistent mechanism, without introducing a new external dependency or service
(no Langfuse, no SaaS, no self-hosted daemon) — a deliberately lighter first step that produces
data any future observability tool could consume without re-instrumenting anything.

---

## Problem

Git It makes LLM calls from five distinct places today, and their logging is inconsistent to the
point of being mostly absent:

- `LiteLLMLLMClient.complete()` (`infrastructure/llm.py`) — used for narrative generation and
  discussion summarization — has **no logging at all**.
- `InstructorCommitAnalysisAdapter.analyze_commit()` (`infrastructure/llm.py`) — the only call
  site with any logging: one `_logger.debug` before the call and one after, with model name and
  duration, but no structured fields, no success/failure distinction beyond exceptions
  propagating, and no token/cost data.
- `InstructorPatternSynthesisAdapter.synthesize()` (`infrastructure/llm.py`) — **no logging**.
- `LiteLLMChatClient.respond()`/`respond_stream()` (`chat/litellm_client.py`) — **no logging** at
  the individual-call level (spec 012 logs one line *per chat request*, aggregating
  `repository_id`, tool-call count, turns used, and total duration — not per underlying LLM
  call, and not for the other four call sites at all).
- The discussion summarizer's underlying LLM call (via `DiscussionSummarizer`, itself using
  `LiteLLMLLMClient`) — inherits `LiteLLMLLMClient`'s lack of logging.

There is currently no way to answer, without reading source code or attaching a debugger: how
many LLM calls did a given ingestion run make, what did it cost, what's the error rate, or which
call site is slow. This is a real operational gap, and it will only get worse once spec 023 (RAG
semantic search) adds a sixth call-site family (embeddings).

---

## Goals

1. One shared function/decorator, `observe_llm_call(call_site: str)`, that any current or future
   client class can apply around its own completion/embedding method — the client classes remain
   otherwise unchanged; this is a cross-cutting wrapper, not a rewrite of any of them.
2. Exactly one structured log record emitted per call, containing: `timestamp`, `call_site`
   (`"commit_analysis" | "pattern_synthesis" | "narrative_generation" | "discussion_summarization"
   | "chat" | "embedding"`), `model`, `duration_ms`, `success: bool`, `error_type: str | None`
   (`type(exc).__name__` on failure, else `None`), `tokens_in`/`tokens_out`/`tokens_total: int |
   None` (best-effort — populated only when the underlying provider response exposes them),
   `estimated_cost_usd: float | None` (best-effort, reusing `api/cost.py`'s existing pricing
   constants where the model/token data allows), and `repository_id: str | None` (when available
   in that call's context).
3. **Never** logs prompt text, response text, or any commit/discussion/user-question content —
   metadata only. This is a locked, non-negotiable requirement (see Security/Privacy), not a
   configurable option.
4. Applied to all five existing call sites (`LiteLLMLLMClient.complete`,
   `InstructorCommitAnalysisAdapter.analyze_commit`, `InstructorPatternSynthesisAdapter.synthesize`,
   `LiteLLMChatClient.respond`/`respond_stream`, and the discussion summarizer's call path through
   `LiteLLMLLMClient`) — plus, once spec 023 ships, the new `LiteLLMEmbeddingClient`.
5. Log destination: Python's standard `logging` module, a dedicated logger name (e.g.
   `git_it.observability`), emitted at `INFO` level via `extra={}` fields — the same structured-
   logging convention this codebase already uses elsewhere (e.g. `_logger.warning(...,
   extra={"repository_id": ...})` in multiple existing modules) rather than introducing a new
   logging library or framework.
6. The wrapper **never suppresses or alters** the underlying call's behavior: on failure, the
   original exception still propagates after the log record is emitted; on success, the original
   return value is returned unchanged. Observability is purely an observer, never a participant.

---

## Non-goals

- Langfuse (self-hosted or cloud), OpenTelemetry, or any other observability SaaS/service
  integration — explicitly deferred by today's decision. This spec produces structured log
  records that *could* later feed such a tool without re-instrumenting any call site, but does
  not integrate one now.
- Distributed tracing or span correlation across a multi-turn agentic conversation. Spec 012's
  existing per-*request* chat log (aggregate tool-call count, turns, total duration) is a
  separate, coarser-grained mechanism and is not replaced by this spec — this spec adds a
  *per-individual-LLM-call* record underneath it.
- A UI or dashboard for viewing these logs.
- Real-time alerting or anomaly detection.
- Guaranteed, universal token-count/cost data — some provider/library code paths may not expose
  token counts; this spec requires the log record to still succeed with those fields absent
  (`None`), not to guarantee their presence.
- Any change to the actual prompts, models, or business logic of any of the five call sites —
  this is a pure logging addition around existing behavior.

---

## Users

- **Operator**: running Git It (locally or in a deployment), wants to know LLM call volume,
  latency, error rate, and approximate cost per call site, without reading source code or adding
  a new external dependency.
- **Future maintainer**: adding a sixth or seventh LLM/embedding call site later, wants a single,
  already-established logging seam to apply rather than re-inventing ad hoc logging each time.

---

## User stories

1. **As an operator**, I want every LLM/embedding call to emit one structured log line, so I can
   grep or aggregate call volume, cost, and error rate per call site without adding new
   infrastructure.
2. **As an operator**, I never want prompt or response content — including repository-derived
   text or a user's own Ask-tab question — to appear in these logs, so local log files never
   accumulate that content unnecessarily.
3. **As a future maintainer**, I want to apply one existing wrapper to a new LLM call site rather
   than writing bespoke logging for it.

---

## Acceptance criteria

```gherkin
Feature: LLM call observability via structured logging

  Scenario: Successful call emits a structured log record
    Given a wrapped LLM call site completes successfully
    When observe_llm_call's wrapper executes
    Then a structured log record is emitted with success=true, error_type=None, and
      duration_ms greater than zero
    And the record's call_site field matches the wrapped call site's identifier

  Scenario: Failing call emits a structured log record and still raises
    Given a wrapped LLM call site raises an exception
    When observe_llm_call's wrapper executes
    Then a structured log record is emitted with success=false and error_type equal to
      type(exc).__name__
    And the original exception is re-raised unchanged after the log record is emitted

  Scenario: Missing token-count data does not break logging
    Given the underlying provider response does not expose token counts
    When a structured log record is emitted for that call
    Then tokens_in, tokens_out, and tokens_total are logged as null/absent
    And no exception is raised by the logging wrapper itself

  Scenario: Prompt and response content never appear in the log record
    Given a call's prompt or response contains a distinctive sentinel string
    When the structured log record is emitted for that call
    Then the sentinel string does not appear anywhere in the log record's fields

  Scenario: A logging failure never breaks the underlying LLM call
    Given the structured-logging step itself raises (e.g. an unexpected serialization error)
    When observe_llm_call's wrapper executes
    Then the underlying LLM call's own result or exception is still returned/raised normally
    And the logging failure is itself caught and logged as a warning, not propagated
```

---

## Domain concepts

- **`LLMCallObservation`** (new frozen dataclass, `infrastructure/observability.py`): the
  structured payload that gets logged. Fields: `call_site: str`, `model: str`, `duration_ms:
  float`, `success: bool`, `error_type: str | None`, `tokens_in: int | None`, `tokens_out: int |
  None`, `tokens_total: int | None`, `estimated_cost_usd: float | None`, `repository_id: str |
  None`. This dataclass exists purely to give the log record a single, reviewable shape — it is
  never persisted to a database, only logged.
- **`observe_llm_call(call_site: str)`** (new decorator/context-manager,
  `infrastructure/observability.py`): wraps a client method. On entry, records a start time; on
  exit (success or exception), builds an `LLMCallObservation`, attempts best-effort extraction of
  token counts from whatever the wrapped call returned (provider-response shape varies — this
  extraction is defensive and never raises on an unexpected shape), estimates cost via
  `api/cost.py`'s existing constants when possible, and emits the log record via the dedicated
  `git_it.observability` logger using `extra={}`. The entire logging step itself is wrapped in
  its own `try/except`, per the "a logging failure never breaks the underlying call" acceptance
  criterion.
- **Application to existing call sites (locked)**: `LiteLLMLLMClient.complete` →
  `call_site="narrative_generation"` or `"discussion_summarization"` (the caller/composition
  layer decides which, since `LiteLLMLLMClient` itself is reused for both — the call site string
  is passed in by whichever composition factory constructs the client for that purpose, not
  hardcoded inside `LiteLLMLLMClient` itself); `InstructorCommitAnalysisAdapter.analyze_commit` →
  `call_site="commit_analysis"`; `InstructorPatternSynthesisAdapter.synthesize` →
  `call_site="pattern_synthesis"`; `LiteLLMChatClient.respond`/`respond_stream` →
  `call_site="chat"`. Once spec 023 ships, `LiteLLMEmbeddingClient.embed` → `call_site=
  "embedding"`.

---

## Inputs and outputs

- `LLMCallObservation(call_site, model, duration_ms, success, error_type, tokens_in, tokens_out,
  tokens_total, estimated_cost_usd, repository_id)` (`infrastructure/observability.py`, frozen
  dataclass)
- `observe_llm_call(call_site: str)` — decorator/context-manager,
  `infrastructure/observability.py`. Wraps existing methods with **no change to their public
  signatures or return types** — purely a cross-cutting concern applied at the call site, not a
  change to any method's contract.

---

## Evidence requirements

Not applicable in the CODEX.md evidence-for-narrative-claims sense — this spec produces
operational logs, not user-facing evidence-linked claims. The log records themselves become the
evidence base for any *future* claim about cost, latency, or reliability ("this ingestion made
14 LLM calls costing $0.02"), which is exactly the gap this spec closes.

---

## Failure modes

| Failure | Expected behavior |
|---|---|
| The wrapped LLM call itself fails | Log record emitted with `success=false`, `error_type=type(exc).__name__`; original exception re-raised unchanged. |
| Provider response doesn't expose token counts | `tokens_in`/`tokens_out`/`tokens_total` logged as `None`; no exception. |
| Cost estimation can't be computed (unknown model, missing token data) | `estimated_cost_usd` logged as `None`; no exception. |
| The logging/observation step itself raises (unexpected data shape, serialization error) | Caught internally, logged as a WARNING with `type(exc).__name__` only; the underlying call's own result/exception is unaffected. |
| `repository_id` not available in a given call's context | Logged as `None`; not treated as an error. |

---

## Security considerations

- **The core security property of this spec is what it does *not* log.** Prompt content,
  response content, commit/discussion summaries, and Ask-tab user question text are never
  included in any log record — enforced by `LLMCallObservation`'s fixed, metadata-only field set
  (there is no "content" or "text" field to accidentally populate).
- No API keys, tokens, or credentials are ever logged, consistent with the existing
  `GITHUB_TOKEN`/`ANTHROPIC_API_KEY` posture elsewhere in this codebase.
- `repository_id` is not treated as sensitive — it is already logged in multiple other places in
  this codebase today.

---

## Privacy considerations

- This spec introduces **no new privacy exposure** — it is strictly more conservative than
  today's status quo, since it replaces ad hoc, inconsistent debug logging with a single,
  metadata-only mechanism that is explicitly forbidden from including content. Logs remain local
  (standard Python `logging`, no new destination or third party) unless the operator configures
  their own log shipping, which is outside this spec's scope.

---

## Observability

(This spec *is* the observability mechanism; there is no meta-observability layer above it.) The
one explicit forward-looking note: because `LLMCallObservation` is a small, stable, metadata-only
shape, a future integration (Langfuse or otherwise) could consume these same log records — via a
log-shipping agent or a second sink added to the `git_it.observability` logger — without
requiring any of the five (soon six) call sites to be touched again. This is documented as a
future path, not built now.

---

## Tests required

### Unit tests (new — a future build batch must write these, TDD, failing first)

- `tests/unit/test_observability.py`:
  - A successful wrapped call emits exactly one log record (via `caplog`, mirroring the existing
    `caplog`-based pattern in `test_narrative_service.py`) with `success=True`, `error_type=None`,
    `duration_ms > 0`, and the correct `call_site`.
  - A failing wrapped call emits a log record with `success=False`, `error_type` equal to the
    raised exception's `type(...).__name__`, **and** the original exception still propagates out
    of the wrapper (assert via `pytest.raises`).
  - A wrapped call whose return value doesn't expose token counts still emits successfully with
    `tokens_in`/`tokens_out`/`tokens_total` as `None`/absent.
  - A wrapped call's prompt/response containing a sentinel string never causes that string to
    appear in the emitted log record's fields (assert on `caplog` record's `extra` dict / message).
  - A deliberately broken observation step (e.g. monkeypatched to raise inside the wrapper's own
    logging logic) does not prevent the underlying call's normal return value or exception from
    propagating; a WARNING is logged instead.
  - One test per existing call site (or one parametrized test enumerating all five) confirming
    each is actually wrapped with the correct `call_site` string, once the implementation batch
    applies the decorator.

### TDD order

Red → Green → Refactor: `LLMCallObservation` shape and `observe_llm_call` wrapper behavior first
(fully testable in isolation with a fake wrapped function), then apply the wrapper to each of the
five real call sites one at a time, re-running the full suite after each to confirm no behavior
change beyond the added log record.

---

## Evaluation required

Not applicable — this is not an LLM-output-quality feature; standard unit tests (above) are the
complete verification strategy.

---

## Documentation impact

- A future build batch creates `docs/progress/{area}/batch-{N}-llm-observability.md` (area:
  likely `infrastructure`, decided at build time).
- `docs/progress/README.md` gets a new entry.
- Each affected module's docstring (or a short note in the relevant progress doc) should mention
  that its LLM/embedding calls are observed via `observe_llm_call`.

---

## ADR impact

**Assessment: likely not ADR-worthy on its own.** This spec does not introduce a new external
dependency, does not change any security or architecture boundary beyond adding a stable,
metadata-only logging shape, and does not alter any existing call site's behavior. It should be
revisited if/when a real observability tool (Langfuse or otherwise) is later integrated — *that*
decision would cross the ADR threshold (new external service, new data-flow-to-a-third-party
question), this one does not.

---

## Open questions

1. **Cost-estimation coverage.** `api/cost.py` currently has pricing constants for the models
   already in use (haiku analysis, Sonnet narrative). Extending `estimated_cost_usd` to the chat
   model and (once spec 023 ships) embedding calls will require adding those models' pricing
   constants there — not addressed by this spec, flagged for the implementation batch.
2. **Call-site string ownership for `LiteLLMLLMClient`.** Since this one class is reused for both
   narrative generation and discussion summarization, the exact mechanism for the *caller*
   (composition factory) to supply the correct `call_site` string — a constructor parameter, a
   wrapper applied at the composition-factory level rather than inside the class itself, or
   something else — is left to the implementation batch to decide; this spec locks the two
   `call_site` string *values* (`"narrative_generation"`, `"discussion_summarization"`), not the
   exact plumbing mechanism.

---

## Out of scope

- Implementation of any kind (the `observe_llm_call` wrapper, `LLMCallObservation`, application
  to the five call sites, tests) — deferred to a future build batch.
- Langfuse or any other observability-tool integration.
- Any change to prompts, models, or business logic of the five wrapped call sites.
- A dashboard, alerting, or log-shipping mechanism.
