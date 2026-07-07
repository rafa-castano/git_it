# Batch 153 — "Refresh all" home dashboard button (spec 028, slice 4 — final)

## Goal

Spec 028 (refresh all repositories) shipped its backend contract across
batches 150-152: `RefreshAllService` (slice 1), the `refresh-all` CLI command
(slice 2), and `POST /api/repos/refresh-all` → `RefreshAllResponse`
(slice 3). This batch adds the last surface the spec requires: a "Refresh
all" button on the dashboard home view that triggers the free commit-corpus
refresh (git fetch + commit-fact extraction only — no LLM calls) for every
already-ingested repository, and reports a concise result summary.

## What was added

- `src/git_it/static/index.html`
  - New `#refresh-all-btn` button in the home view, in the
    "Previously analyzed" label row (`.repo-cards-label`) above the repo
    card grid — a collection-level action alongside the repo count, not a
    per-repo action. Reuses the existing `hdr-btn` class (no new CSS). No
    visibility gating: the button is always present on the home view,
    since refresh-all applies to the whole tracked-repo collection and the
    backend already reports "nothing to refresh" (a zeroed response) when
    there are zero repositories — the simplest correct behavior, avoiding
    a second client-side empty-state branch.
  - A companion `#refresh-all-status` span (empty by default,
    `aria-live="polite"`) next to the button for the busy/result/error
    message, mirroring `#ingest-status`'s live-region pattern.
- `src/git_it/static/app.js`
  - `_doRefreshAll()` — the click handler, wired the same busy/POST/result
    style as `_doBackfillEmbeddings()` (batch 148): disables the button and
    shows a busy label (`Refreshing…`) while in flight, `POST`s to
    `/api/repos/refresh-all` with the same
    `fetch(...) + Content-Type: application/json` pattern used by every
    other write call in this file (no `Authorization`/API-key header,
    matching the existing dashboard — the backend's bearer-key dependency
    only activates when `GIT_IT_API_KEY` is set server-side).
    - **Success**: renders a concise summary via `statusEl.textContent`
      (never `innerHTML`) — `Refreshed N of M repositories · X new commits
      · Y failed` — built only from the response's numeric counts
      (`refreshed_count`, `total_repositories`, `total_new_commits`,
      `failed_count`). The response's `repositories[].canonical_url` /
      `safe_message` fields are deliberately **not** surfaced in this
      summary (out of scope for the concise collection-level message the
      task called for), so no server-sourced string is ever interpolated
      into the DOM — the untrusted-input posture (CODEX.md) is satisfied
      by construction, not by an escaping step.
    - **Zero repositories** (`total_repositories === 0`): shows
      "Nothing to refresh yet — add a repository first." instead of a
      generic zero-count summary.
    - **Non-2xx / network failure**: shows a "try again" message, re-enables
      the button, and does not touch the repo list.
    - On success, re-runs `loadRepos()` (refreshes the sidebar/`reposCache`)
      followed by `renderRepoCards()` (rebuilds the home grid) — the same
      two-call sequence `_pollForRepo`'s completion path already uses — so
      any repository whose commit count grew is reflected immediately.

## Tests added

`tests/unit/test_api_static_refresh.py` (new file, per the batch brief —
`test_api_static.py` was left untouched, it carries pre-existing uncommitted
line-ending state unrelated to this batch):

- `test_static_app_js_has_refresh_all_click_handler_that_posts` — pins that
  `_doRefreshAll` exists and issues a `POST` to `/api/repos/refresh-all`.
- `test_static_app_js_refresh_all_reloads_repo_list_on_success` — pins that
  the handler re-runs `loadRepos()` so the home grid picks up new commit
  counts.
- `test_static_index_has_refresh_all_button` — pins that `#refresh-all-btn`
  is present in `index.html`.
- `test_static_index_refresh_all_button_calls_click_handler` — pins the
  `onclick="_doRefreshAll()"` wiring on the button element.

**TDD**: ran the new test file before any implementation — all 4 failed
(`AssertionError`/`IndexError`, since none of the identifiers existed yet).
After implementing the HTML button/status span and the `app.js` handler, all
4 pass. Full suite: `1164 passed, 33 skipped` (no regressions).

## Gotchas

- `loadRepos()` alone only rebuilds the sidebar (`renderSidebarRepos()`); it
  does not touch the home grid. `renderRepoCards()` must be called
  explicitly afterward — the same two-step sequence already used at the end
  of `_pollForRepo`'s `onTick`. Missing the second call would leave the home
  cards showing stale commit counts after a successful refresh.
- The success-summary intentionally omits the per-repository
  `canonical_url`/`safe_message` detail the endpoint returns — the batch
  brief asked for a concise collection-level line, and leaving those fields
  out entirely means there is no string interpolation to sanitize in this
  handler at all (simpler and safer than escaping).
- This batch does not touch `api/routes/`, `api/schemas.py`,
  `interfaces/cli.py`, or any `application/` code — the backend contract
  shipped in batches 150-152 was used as-is.

## Commits

Not committed by this batch — left in the working tree per the
orchestrator's collision-avoidance instructions (a human + Codex share this
repo). The orchestrator reviews, runs the gates, drives Playwright
verification, and commits.
