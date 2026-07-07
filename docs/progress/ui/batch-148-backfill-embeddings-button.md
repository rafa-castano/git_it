# Batch 148 — Embedding backfill dashboard button (spec 027, slice 4 — final)

## Goal

Spec 027 (embedding backfill) shipped its backend contract in batch 147:
`GET /api/repos/{id}/backfill-embeddings` (`{available, missing}`) and
`POST /api/repos/{id}/backfill-embeddings` (`{embedded, already_present, failed}`
on success, `503 {"detail": "...OPENAI_API_KEY..."}` when no key is configured).
This batch adds the last surface the spec requires: the per-repo dashboard
control (AC "Dashboard control visibility") — shown only when a key is
configured **and** at least one already-analyzed item is missing an
embedding, hidden in every other case.

## What was added

- `src/git_it/static/index.html`
  - New `#sh-backfill-btn` button in the repo-detail header, next to
    `#sh-analyze-btn`/`#sh-delete-btn`. Reuses the existing `analyze-btn`
    class (no new CSS). Hidden by default (`style="display:none"`), matching
    the existing `#sh-delete-btn` convention — JS decides when to reveal it.
- `src/git_it/static/app.js`
  - `_loadBackfillStatus(repoId)` — mirrors `_loadAnalyzeEstimate`'s shape:
    called from `renderHeaderRepoMeta()` right after `_loadAnalyzeEstimate`.
    Hides the button immediately (so a previous repo's label never flashes
    while the new repo's status is in flight), fetches
    `GET /api/repos/{id}/backfill-embeddings` via the existing `apiFetch`
    helper, and reveals the button — with the missing count in its label
    (`Enable semantic search (N)`) — **only** when
    `status.available && status.missing > 0` (the locked visibility rule,
    kept as one literal condition so a regression dropping either half of
    the AND is easy to catch). A repo-switch race is guarded by re-checking
    `currentRepo === repoId` after the await resolves.
  - `goHome()`: also hides `#sh-backfill-btn`, mirroring how it already hides
    `#sh-delete-btn` when leaving the repo-detail view.
  - `_doBackfillEmbeddings()` — the click handler, wired the same way
    `_doAnalyze`/`_generateCaseStudy` are: disables the button and shows a
    busy label (`Computing embeddings…`) while in flight, then `POST`s to the
    run endpoint with the same `fetch(...) + Content-Type: application/json`
    pattern used by every other write call in this file (no
    `Authorization`/API-key header anywhere in `app.js` today — confirmed by
    search before writing this — consistent with the spec note that the
    dashboard's bearer-key gate is opt-in server-side and irrelevant for
    local use). Unlike `+ Analyze`/case-study regenerate, the backend
    contract for this endpoint is **synchronous** (no background job / no
    `_analyze_bg`-style progress state), so there is no polling loop — the
    response body carries the final counts directly.
    - **Success**: shows `Embedded N, M already present, K failed` via
      `btn.textContent` (never `innerHTML` — the counts are untrusted-origin
      numbers by the CODEX.md posture even though the schema types them as
      `int`), then re-runs `_loadBackfillStatus` so the button hides itself
      once `missing` has dropped to 0.
    - **503** (no `OPENAI_API_KEY`): shows a non-alarming
      "Semantic search needs an OpenAI key" label instead of a generic error,
      matching the spec's "never an error" posture for the no-key case.
    - **Other non-2xx / network failure**: shows a "try again" message and
      re-enables the button.

## Tests added

`tests/unit/test_api_static_backfill.py` (new file, per the batch brief —
`test_api_static.py` was left untouched):

- `test_static_app_js_wires_backfill_status_endpoint` — pins the GET status
  wiring (`/backfill-embeddings` + `_loadBackfillStatus`).
- `test_static_app_js_gates_backfill_button_on_available_and_missing` — pins
  the exact `status.available && status.missing > 0` visibility condition.
- `test_static_app_js_has_backfill_click_handler_that_posts` — pins that
  `_doBackfillEmbeddings` exists and issues a `POST` to the same endpoint.
- `test_static_app_js_handles_no_key_503_response` — pins that the 503 case
  is handled explicitly (not folded into the generic error branch).
- `test_static_index_has_backfill_button_hidden_by_default` — pins that
  `#sh-backfill-btn` starts with `display:none`.
- `test_static_index_backfill_button_calls_click_handler` — pins the
  `onclick="_doBackfillEmbeddings()"` wiring on the button element.

**TDD**: ran the new test file before any implementation — all 6 failed
(`IndexError`/`AssertionError`, since none of the identifiers existed yet).
After implementing the HTML button and the two `app.js` functions, all 6
pass. Full suite: `1142 passed, 33 skipped` (no regressions).

## Gotchas

- The GET status call race: if a user clicks between two repos quickly, an
  in-flight `_loadBackfillStatus` from the previously selected repo could
  otherwise resolve after `currentRepo` has changed and show the wrong
  repo's button state. Guarded the same way `refreshCurrentRepoMeta` already
  does elsewhere in this file — re-check `currentRepo === repoId` after the
  `await`.
- The POST response's numeric fields are assigned via `btn.textContent =`
  (never innerHTML), so no sanitization step was needed — template-literal
  interpolation into `textContent` cannot execute markup regardless of what
  the numbers actually contain.
- This batch does not touch `api/routes/`, `api/schemas.py`,
  `interfaces/cli.py`, or any `application/` code — the backend contract
  shipped in batch 147 was used as-is.

## Commits

Not committed by this batch — left in the working tree per the orchestrator's
collision-avoidance instructions (a human + Codex share this repo). The
orchestrator reviews, runs the gates, drives Playwright verification, and
commits.
