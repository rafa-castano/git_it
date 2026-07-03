## Batch 101 — Background-job fail-loud (spec 021)

### Goal

Close part (a) of the ADR 010 limitation: the in-process `_analyze_bg` and
`_regen_bg` daemon-thread workers in `src/git_it/api/routes/repos.py` caught
`Exception` broadly and, on failure, simply flipped their in-memory progress dict
back to `{"running": False, ...}`. The status endpoints then reported
`running: false` — indistinguishable from "finished successfully," "never
started," and "crashed." The frontend polls those endpoints and, on
`running: false`, silently treated the job as done. A failed analysis or
case-study regeneration produced no user-visible signal at all.

This batch surfaces background-job failure as a distinct, machine-readable state
(`error: <ExceptionTypeName> | null`) through the existing status endpoints, and
makes the frontend show a FAILED state instead of silently succeeding — without
ever leaking the raw exception message, args, repr, or traceback.

### What was added

**`src/git_it/api/schemas.py`** — added `error: str | None = None` to both
`AnalyzeStatusResponse` and `RegenStatusResponse`. The default keeps every
existing caller and every pre-existing test that never sets an error working
unchanged (backward-compatible optional field).

**`src/git_it/api/routes/repos.py`**

- `_analyze_bg` — the outer `except Exception` now records `error_type =
  type(e).__name__` (sanitized, type name only) and the `finally` block writes it
  into the progress dict under a new `"error"` key. The initial "running" seed
  sets `"error": None`. The nested narrative-generation failure inside a
  *successful* analysis is unchanged (it still logs only — the analysis itself
  succeeded, so the job did not fail).
- `_regen_bg` — same posture: capture `type(e).__name__` in the except, write it
  under `"error"` in the finally, seed `"error": None` on start.
- `get_analyze_status` / `get_regen_status` — surface `error=p.get("error")` /
  `error=state.get("error")`. Using `.get()` (not `["error"]`) means entries
  seeded by older code paths or existing tests without an `"error"` key report
  `error: None` instead of crashing with `KeyError`.

**`src/git_it/static/app.js`**

- `_pollAnalyzeStatus` — captures a `failedError` across poll ticks; when the job
  stops (`!s.running`) with a non-null `s.error`, `onDone` renders a
  "Analysis failed" button state (red, re-enabled, with a `title` naming the
  sanitized error type) instead of the "✓ Done!" success path, then resets after
  6s.
- `_pollRegenStatus` — same pattern: on a failed regen it renders a
  `role="alert"` "Case study generation failed (&lt;type&gt;)" message in
  `case-study-content` instead of silently calling `loadCaseStudy`. The error type
  is passed through `esc()` as defense-in-depth even though the backend only ever
  sends a sanitized class name.

### Tests added

Written RED-first (10 failing, then made green), mocking the background worker's
dependency and calling `_analyze_bg` / `_regen_bg` **synchronously** (no real
threads) — the isolation posture established in batch 100.

- `tests/unit/test_api_analyze.py` (5 new):
  `test_analyze_status_error_is_none_by_default`,
  `test_analyze_status_error_is_none_when_progress_has_no_error_key`,
  `test_analyze_bg_failure_surfaces_sanitized_error_type_in_status`,
  `test_analyze_bg_failure_never_leaks_raw_exception_message` (secret-leak guard),
  `test_analyze_bg_success_leaves_error_none`.
- `tests/unit/test_api_regen.py` (new file, 5 tests): the regen mirror of the
  above, including `test_regen_bg_failure_never_leaks_raw_exception_message`.

Both secret-leak guards feed an exception whose message embeds `sk-SECRET123` and
assert that string is absent from the entire status response body while the
sanitized type name (`RuntimeError`) is present.

Full suite: **811 passed, 18 skipped** (was 801 before this batch; +10 new).

### Gotchas

- **Spec header said "Implemented" before the code existed.** The spec file
  (`specs/021-background-job-fail-loud.md`) was authored in the same RED pass as
  the tests and optimistically carried `Status: Implemented`. That is now true as
  of this commit; the header was left as-is rather than churned Draft→Implemented
  across two commits.
- **Type name only, never `str(exc)`.** The raw exception message can carry
  provider API keys, DB connection strings, and filesystem paths. The sanitized
  `type(e).__name__` posture matches the existing convention already in this file
  (`_fetch_and_store_repo_metadata`, `_ingest_bg`) and spec 014's 503 handler. The
  regression tests lock this in.
- **`.get("error")`, not `["error"]`.** Several pre-existing analyze tests seed
  the progress dict directly without an `"error"` key
  (`test_analyze_status_returns_live_progress` et al). Reading with `.get()` keeps
  them green and lets the field default to `None`.
- **Non-durable state is still non-durable.** The progress dicts remain in-memory
  and per-process. A restart still loses in-flight error state — that is the
  explicit ADR 010 non-goal this batch does *not* address.

### Commits

- `feat: surface background-job failures via status endpoints (spec 021)`
