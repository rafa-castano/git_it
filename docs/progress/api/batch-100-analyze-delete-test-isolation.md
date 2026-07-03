## Batch 100 — Fix `_analyze_progress` test-isolation flake between analyze and delete tests

### Goal

Batch 99 flagged (but explicitly left out of scope) a full-suite-only flake:
`tests/unit/test_api_delete.py::test_delete_repo_success` intermittently returned `409`
instead of `200` when the full suite ran in file order, but always passed in isolation.
This batch fixes that flake — a pure test-isolation defect, not a production bug.

### Root cause

`src/git_it/api/routes/repos.py` holds module-level dicts `_analyze_progress` and
`_regen_progress` as the in-memory progress store for background analyze/regenerate work,
shared across the whole pytest session (not per-app/per-`TestClient` state).

`POST /api/repos/repo-abc/analyze` spawns a real daemon thread running `_analyze_bg`,
which sets `_analyze_progress["repo-abc"]["running"] = True` and only flips it back to
`False` in a `finally` block once the (real, unmocked) analysis work finishes or fails.
Three tests in `tests/unit/test_api_analyze.py` POST to this endpoint with the default
repository id `"repo-abc"` and no mocking of the background worker:
`test_analyze_returns_analyzing_status`, `test_analyze_accepts_any_litellm_model`, and
`test_analyze_accepts_valid_auth` (a third leak site beyond the two originally
flagged in batch 99 — found by auditing the whole file for POSTs to `/analyze`).

Later, `tests/unit/test_api_delete.py::test_delete_repo_success` deletes the same
default id `repo-abc`. `delete_repo`'s guard — "block deletion while an analysis is in
progress" — is correct, production behavior; it saw the leaked `running=True` from an
earlier test's still-in-flight (or not-yet-cleaned-up) background thread and returned
`409` instead of `200`. The production guard was not touched — only the test-side leak.

### What was added

**`tests/unit/test_api_analyze.py`** — the three tests that POST to `/analyze` and thereby
spawn a real `_analyze_bg` thread now `monkeypatch.setattr(repos_module, "_analyze_bg",
lambda *args, **kwargs: None)` before making the request. The endpoint still spawns a real
`threading.Thread` (matching production wiring exactly), but its target is a no-op, so no
real analysis/LLM/DB work runs and `_analyze_progress` is never mutated. This keeps each
test's original assertion intent (the endpoint's immediate "ANALYZING" response) fully
intact while removing the only source of the leak.

This mirrors, but is not identical to, the existing seam in
`tests/integration/conftest.py` (`_SyncThread` replacing `repos_module.threading` so the
worker runs synchronously). That integration fixture is used because those tests *want* the
worker's DB side effects to happen deterministically. These unit tests want the opposite —
no worker side effects at all — so a no-op target on the real thread is the more precise
choice: it verifies the request/response contract without pulling in the real analysis
service (no API key/LLM mocking exists in this file, so running it for real risked network
calls or slow/nondeterministic failures inside the try/except in `_analyze_bg`).

**`tests/unit/conftest.py`** (new file) — an `autouse=True` fixture that `.clear()`s
`_analyze_progress` and `_regen_progress` before and after every test under
`tests/unit/`. This is the safety net: even if a future test spawns a real thread and
forgets to mock it, or timing changes, no leaked state can survive into the next test.
Imports the dicts from `git_it.api.routes.repos` and clears them in place (not rebinding),
since several existing tests already hold references to the same dict objects (e.g.
`test_analyze_status_returns_live_progress` imports `_analyze_progress` directly and
seeds it, relying on identity).

No production code in `repos.py` was changed — the module-level dicts, the analyze/regen
background functions, and the delete-repo concurrency guard are all as before.

### Tests added

No new test cases — this batch is a test-infrastructure fix for existing tests. Three
existing tests gained a `monkeypatch.setattr` line; one new fixture file added.

### Verification

- `uv run pytest tests/unit/test_api_delete.py::test_delete_repo_success -q` — passes in
  isolation (baseline, unchanged).
- `uv run pytest -q` run three times in a row: **801 passed, 18 skipped** each time (up
  from 800 passed/1 failed before the fix — the extra pass is
  `test_delete_repo_success` now succeeding deterministically instead of flaking).
- `uv run ruff check .` — all checks passed.
- `uv run ruff format --check .` — all files formatted (ruff's `--fix` reordered the new
  `import git_it.api.routes.repos as repos_module` lines in `test_api_analyze.py` to sort
  correctly relative to the existing `from git_it.api.app import create_app` imports).
- `uv run mypy src/` — no issues found in 50 source files.

### Gotchas

- The leak had a third source (`test_analyze_accepts_valid_auth`) beyond the two batch 99
  named — always audit every POST to a thread-spawning endpoint in a file, not just the
  ones a prior note called out.
- The fix is deliberately two-layered: mocking `_analyze_bg` removes the real thread's
  side effects at the source (deterministic, no reliance on timing), while the autouse
  `conftest.py` fixture guarantees isolation regardless of test order or future tests that
  might reintroduce a similar leak. Either alone would have been enough for today's flake;
  both together make the suite robust against tomorrow's.

### Commits

- `test: fix _analyze_progress cross-test leak between analyze and delete tests`
