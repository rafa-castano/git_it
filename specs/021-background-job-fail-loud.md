# Feature Spec: Background-Job Fail-Loud

**Status:** Implemented
**Spec number:** 021
**Author:** Rafael Castaño
**Date:** 2026-07-03

---

## Summary

Make failures in the analyze and case-study-regenerate background jobs visible to the caller
through the existing status endpoints, without leaking secrets or internal details. This closes
part (a) of the ADR 010 limitation: in-process background work currently swallows exceptions and
reports `running: False`, indistinguishable from "finished successfully" or "never started."

---

## Problem

`_analyze_bg` and `_regen_bg` in `src/git_it/api/routes/repos.py` run on daemon threads spawned by
`POST /api/repos/{repository_id}/analyze` and `POST /api/repos/{repository_id}/case-study/regenerate`.
Both catch `Exception` broadly and, on failure, simply flip the in-memory progress dict back to
`{"running": False, ...}`. The status endpoints (`GET .../analyze/status`, `GET
.../case-study/regen-status`) then report `running: False` with no way to distinguish "job
finished successfully," "job never started," and "job crashed." The frontend polls these
endpoints and, on `running: false`, silently treats it as success — the user sees no indication
that anything went wrong.

---

## Goals

1. Surface background-job failure as a distinct, machine-readable state via the existing status
   endpoints — `error: <ExceptionTypeName> | null`.
2. Never leak the raw exception message, `args`, `repr`, or traceback — only the sanitized
   exception **type name**.
3. Show a clear "failed" state in the frontend when a poll returns `running: false` with a
   non-null `error`, instead of silently treating it as done.
4. Log the failure (sanitized type name only) server-side for operator visibility.

---

## Non-goals

- Durable/persistent job state. The progress dicts remain in-memory, per-process, non-restart-safe
  — unchanged from today. A restart or process crash still loses in-flight progress/error state.
  This is documented explicitly as future work (see ADR 010).
- Retry / auto-resume of failed jobs.
- Structured error codes or categorization beyond the Python exception type name.
- Changing the in-progress delete-blocking guard (`_analyze_progress`/`_regen_progress` `running`
  checks in `delete_repo`) — that behavior is untouched.

---

## Users

All users of the git_it local-first UI who trigger commit analysis or case-study regeneration.

---

## User stories

1. **As a user**, when a triggered analysis job fails (e.g. the LLM provider is unreachable, a
   malformed response, a DB error), I want the UI to tell me it failed instead of silently doing
   nothing, so I know to retry or investigate.
2. **As a user**, when a case-study regeneration fails, I want the same clear failure signal.
3. **As an operator**, I want the failure type logged server-side so I can correlate user reports
   with server logs, without any secret leaking into logs or API responses.

---

## Acceptance criteria

```gherkin
Feature: Background-job fail-loud

  Scenario: Analyze background job failure surfaces via status endpoint
    Given an analysis job is triggered for a repository
    And the background worker raises an exception during execution
    When the client polls GET /api/repos/{repository_id}/analyze/status
    Then the response has running: false
    And the response has error: "<ExceptionTypeName>"

  Scenario: Regen background job failure surfaces via status endpoint
    Given a case-study regeneration job is triggered for a repository
    And the background worker raises an exception during execution
    When the client polls GET /api/repos/{repository_id}/case-study/regen-status
    Then the response has running: false
    And the response has error: "<ExceptionTypeName>"

  Scenario: Successful job reports error: null
    Given an analysis or regen job completes without raising
    When the client polls the corresponding status endpoint
    Then error is null

  Scenario: Raw exception content never reaches the API
    Given the background worker raises an exception whose message contains
      a secret-looking string (e.g. an API key)
    When the client polls the status endpoint
    Then the secret string never appears anywhere in the response body

  Scenario: Frontend shows a failed state
    Given the analyze or regen poll receives running: false with a non-null error
    When the frontend processes that poll response
    Then it shows a clear "failed" message naming the sanitized error type
    And it does not silently behave as if the job succeeded
```

---

## Domain concepts

- **Sanitized error**: `type(exc).__name__` only — e.g. `"RuntimeError"`, `"LiteLLMException"`.
  Never `str(exc)`, `exc.args`, `repr(exc)`, or a traceback. This matches the existing posture
  elsewhere in `repos.py` (the `type(e).__name__` logging in `_fetch_and_store_repo_metadata` and
  `_ingest_bg`, and the "never leak raw error" comments on the chat endpoints) and spec 014's 503
  sanitization for the chat service.
- **In-memory progress store**: unchanged data structure (`_analyze_progress`,
  `_regen_progress` module-level dicts protected by their existing locks), extended with one new
  key: `"error": str | None`.

---

## Inputs and outputs

### `GET /api/repos/{repository_id}/analyze/status`

**Response 200 (unchanged fields + new `error`):**
```json
{ "running": false, "done": 3, "total": 5, "pct": 60, "error": "RuntimeError" }
```
`error` is `null` when there is no recorded failure (including the "never started" and
"succeeded" cases).

### `GET /api/repos/{repository_id}/case-study/regen-status`

**Response 200 (unchanged fields + new `error`):**
```json
{ "running": false, "audience": "beginner", "error": "RuntimeError" }
```

No request/response shape changes to the `POST /analyze` or `POST .../regenerate` trigger
endpoints themselves — only the status/read endpoints gain the `error` field.

---

## Evidence requirements

- Unit tests invoke `_analyze_bg` / `_regen_bg` directly with a mocked dependency that raises, then
  assert the corresponding status endpoint reports `running: false` and `error: "<TypeName>"`.
- A dedicated regression test feeds an exception whose message contains a fake secret
  (`"sk-SECRET123"`) and asserts that string is absent from the status response body.
- Existing tests that seed the progress dicts directly without an `"error"` key (e.g.
  `test_analyze_status_returns_live_progress`) must continue to pass unchanged — `error` defaults
  to `None` via `.get("error")`, not a required dict key.

---

## Failure modes

| Failure | Expected behavior |
|---------|------------------|
| Analysis background job raises | `analyze/status` → `running: false`, `error: "<TypeName>"`; failure logged at WARNING with type name only |
| Regen background job raises | `regen-status` → `running: false`, `error: "<TypeName>"`; failure logged at WARNING with type name only |
| Job succeeds | `error: null` |
| Job never started for this repo id | `error: null` (unchanged "unknown repo" default response) |
| Process restarts mid-job | Progress/error state is lost (in-memory only) — documented non-goal, unchanged from today |

---

## Security considerations

- The exception **type name** is considered safe to expose (matches existing convention across
  this file). The exception **message, `args`, `repr()`, and traceback are never** stored in the
  progress dict, logged beyond the type name, or returned in any API response — they may carry
  provider API keys, DB connection strings, file system paths, or repository internals.
- This is validated with an explicit regression test asserting a fake-secret string never appears
  in the status response.
- No new write/auth surface — the status endpoints were already unauthenticated reads (matching
  existing `analyze/status` and `regen-status` behavior); only field content changes.

---

## Privacy considerations

No new personal data is captured. The sanitized error field contains only a Python exception
class name, never user- or repository-specific content.

---

## Observability

Failures are logged server-side at WARNING level with the sanitized exception type name and the
`repository_id`, using the existing `_logger` conventions already present in this file (e.g.
`_logger.warning("analysis failed: %s", type(e).__name__, extra={"repository_id": repository_id})`).

---

## Tests required

### Unit tests (new)

`tests/unit/test_api_analyze.py`:
1. `test_analyze_status_error_is_none_by_default`
2. `test_analyze_status_error_is_none_when_progress_has_no_error_key`
3. `test_analyze_bg_failure_surfaces_sanitized_error_type_in_status`
4. `test_analyze_bg_failure_never_leaks_raw_exception_message` (secret-leak guard)
5. `test_analyze_bg_success_leaves_error_none`

`tests/unit/test_api_regen.py` (new file):
1. `test_regen_status_defaults_when_no_regen_running`
2. `test_regen_status_error_none_when_progress_has_no_error_key`
3. `test_regen_bg_failure_surfaces_sanitized_error_type_in_status`
4. `test_regen_bg_failure_never_leaks_raw_exception_message` (secret-leak guard)
5. `test_regen_bg_success_leaves_error_none`

### TDD order

Red → Green → Refactor for each test listed above.

---

## Evaluation required

None beyond automated tests. No LLM output is generated or altered by this change.

---

## Documentation impact

- Create `docs/progress/api/batch-101-background-job-fail-loud.md`.
- Add entry to `docs/progress/README.md` (API section).

---

## ADR impact

None new. This closes part (a) of the limitation already tracked under ADR 010 (in-process,
non-durable background job state) — scoped strictly to in-process failure surfacing, not durable
job storage. The non-durable limitation itself remains and is explicitly out of scope here.

---

## Open questions

None — all decisions resolved:
- Error content: exception type name only, never raw message/args/traceback.
- Storage: extend existing in-memory progress dicts with one new key, no new persistence.
- Frontend behavior: show a distinct "failed" state on `running: false` + non-null `error`.
