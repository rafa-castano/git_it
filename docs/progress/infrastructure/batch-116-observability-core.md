## Batch 116 — LLM call observability core (spec 024, slice 1)

### Goal

Build the core observability mechanism for spec 024 (LLM Call Observability) in
isolation: the `LLMCallObservation` frozen dataclass and the `observe_llm_call`
decorator factory. This batch does **not** apply the decorator to any of the
five real LLM call sites — that is batch 117, a separate, later slice.

### Why

Spec 024 (`docs/specs/024-llm-call-observability.md`) locks the TDD order: build and
fully test the wrapper in isolation with a fake wrapped function first, then
apply it to each real call site one at a time. This keeps the mechanism itself
small, reviewable, and independently green before it touches any production
code path.

### What was added

**`infrastructure/observability.py`** (new)
- `LLMCallObservation` — frozen dataclass, the structured, metadata-only log
  payload: `call_site`, `model`, `duration_ms`, `success`, `error_type`,
  `tokens_in`, `tokens_out`, `tokens_total`, `estimated_cost_usd`,
  `repository_id`. Never persisted — only logged.
- `observe_llm_call(call_site: str)` — decorator factory for sync instance
  methods. Records `time.monotonic()` before calling the wrapped function,
  captures success/exception, builds an `LLMCallObservation`, and emits it via
  the dedicated `git_it.observability` logger at `INFO` using `extra={}`. On
  exception, the original exception is always re-raised unchanged after the
  log record is emitted. On success, the original return value passes through
  unchanged.
- `_emit_observation` — small, separately-callable helper that does the actual
  `_observability_logger.info(...)` call, kept as a module-level function
  specifically so tests can monkeypatch it to simulate a broken observation
  step (per the spec's "a logging failure never breaks the underlying call"
  acceptance criterion).
- `_build_and_emit` — wraps observation construction + emission in its own
  `try/except Exception`; on failure it logs a WARNING via the module's own
  `_logger` (`observability logging failed: %s`, `type(log_exc).__name__`) and
  swallows the failure — it never propagates past the decorator.
- Best-effort duck-typed extraction: `model` via `getattr(self, "_model",
  "unknown")`; `repository_id` via `getattr(self, "_repository_id", None)`,
  falling back to `getattr(self, "repository_id", None)`.

### Tests added

`tests/unit/test_observability.py` (11 tests, all new):
- Successful call emits exactly one `git_it.observability` log record with
  `success=True`, `error_type=None`, `duration_ms > 0`, correct `call_site` and
  `model`, and the original return value passes through unchanged.
- Failing call emits a record with `success=False`, `error_type ==
  "ValueError"`, and the original exception still propagates (`pytest.raises`).
- A call on an instance with no `_model` attribute logs `model == "unknown"`.
- `tokens_in`/`tokens_out`/`tokens_total`/`estimated_cost_usd` are all `None`
  (best-effort extraction is out of scope for this batch — see Gotchas).
- `repository_id` is `None` when absent, and correctly populated when a
  `_repository_id` attribute is present on the wrapped instance (duck-typing
  proven both ways).
- No content leakage: a distinctive sentinel string passed as an argument (and
  present in the return value / exception message) never appears in the log
  record's message or `extra`/`__dict__`, checked on both the success and
  failure paths.
- A monkeypatched, deliberately broken `_emit_observation` does not prevent the
  wrapped call's own return value or exception from propagating correctly, and
  logs a WARNING mentioning "observability" instead.
- `functools.wraps` preserves the decorated method's `__name__`.

Full suite: **885 passed, 21 skipped** (was 874 passed / 21 skipped before this
batch; +11 new passing tests, no regressions).

### Gotchas

- **`tokens_in`/`tokens_out`/`tokens_total`/`estimated_cost_usd` are `None` in
  practice for all five current call sites, by design.** Every existing
  `LiteLLMLLMClient.complete()` returns a plain unwrapped `str` (discarding
  `response.usage` before returning); `InstructorCommitAnalysisAdapter` and
  `InstructorPatternSynthesisAdapter` return parsed Pydantic models via
  `instructor`, not the raw completion object. A generic decorator wrapping
  these *public* methods cannot reliably recover token-usage data from the
  return value alone — this is exactly the scenario spec 024's acceptance
  criteria calls out ("Given the underlying provider response does not expose
  token counts... tokens are logged as null/absent... no exception is
  raised"). This is intentional, spec-compliant behavior, not a shortcut to
  revisit later without a design change (e.g. rewriting call sites to preserve
  raw provider responses, which the spec explicitly puts out of scope: "No
  change to prompts, models, or business logic").
- **`repository_id` is generically `None` for all five call sites today**,
  because none of their classes are repo-scoped instances — they're all
  model-scoped (`self._model` only). The duck-typed `_repository_id`/
  `repository_id` lookup exists so a future repo-scoped client (or an adapter
  wrapping one) can opt in without any change to `observe_llm_call` itself.
- The Windows sandbox environment used for this batch has coarse
  `time.monotonic()` resolution (observed ~60ms granularity rather than
  sub-millisecond) — a fake wrapped call needs an actual `time.sleep(0.1)` (not
  a 1-5ms sleep) to reliably produce `duration_ms > 0` in tests; a shorter
  sleep intermittently measured `0.0`. Documented here in case a future test
  in this area seems to flake for no obvious reason.
- `observe_llm_call` only supports sync methods, matching the spec's explicit
  scope (none of the five real call sites are async).

### Commits

- `feat: add LLM call observability core (observe_llm_call, spec 024)`
