# Batch 87 — "Generate case study" button in the empty Case Study tab

## Goal

When a repository had analyzed commits but no case-study narrative yet, the
Case Study tab's 404 empty state only said "No case study generated yet. Run
analysis first." — even though the commits were already analyzed and a
narrative-only regeneration was possible via the existing
`POST /api/repos/{id}/case-study/regenerate` endpoint (which does not
re-run commit analysis). Add a "Generate case study" button for that specific
case, gated on the repo actually having analyzed commits.

## What changed

- `src/git_it/static/app.js`
  - `loadCaseStudy(repoId)`: restructured the 404 branch. It still falls back
    to `beginner` when a non-default audience 404s (unchanged). For a true
    "no narrative at all" 404, it now checks
    `currentRepoMeta.analysis_count > 0` (populated by `selectRepo()` from
    the repo-list payload before `loadCaseStudy` is ever called) to decide
    which empty state to render:
    - **Has analyzed commits, no narrative** → empty state with a
      "Generate case study" button wired to a new `_generateCaseStudy(repoId)`.
    - **No analyzed commits** → unchanged "Run analysis first" message, no
      button (matches the locked decision: don't offer narrative generation
      when there's nothing analyzed to narrate).
  - New `_generateCaseStudy(repoId)`: shows a spinner + "Generating case
    study… this may take a minute." message, `POST`s to
    `/api/repos/{id}/case-study/regenerate` with the currently selected
    audience (`localStorage['cs-audience']`, default `beginner` — same
    default `loadCaseStudy` itself uses), and on success hands off to the
    **existing** `_pollRegenStatus(repoId, audience)` polling loop (already
    used by `_setCsAudience` for audience switching) which polls
    `GET /api/repos/{id}/case-study/regen-status` every 2s and reloads the
    case study via `loadCaseStudy(repoId)` once generation finishes. No new
    polling logic was written — this is a straight reuse of the audience-
    switch code path, since both flows hit the same regenerate/regen-status
    endpoints with the same "no commit re-analysis" contract.
    Network/HTTP failures render the same error-empty-state pattern already
    used elsewhere (`_setCsAudience`, `_doAnalyze`).
  - No backend changes — both endpoints (`/case-study/regenerate`,
    `/case-study/regen-status`) already existed and were unmodified.

## Tests / verification

- No JS test harness exists in this repo — none was added.
- `uv run pytest -q` — 723 passed, 12 skipped (frontend-only change, backend
  untouched).
- `uv run ruff check .` / `uv run ruff format --check .` — no findings.
- `node --check src/git_it/static/app.js` — exits 0.
- Static verification: confirmed `currentRepoMeta` is set (from
  `reposCache.find(...)`) in `selectRepo()` *before* `loadCaseStudy(repoId)`
  is invoked, so `analysis_count` is available at the time the empty state
  decides whether to show the button. Confirmed the regenerate/regen-status
  endpoint contracts (`src/git_it/api/routes/repos.py`) match what
  `_generateCaseStudy` and the reused `_pollRegenStatus` expect (POST body
  `{audience}`, `RegenStatusResponse{running, audience}`).
- Live/visual verification (clicking the button, watching the poll loop,
  confirming the narrative loads) was **not** performed — Playwright MCP
  browser tools were not exercised in this session. This is a
  static-inspection-only verification for this batch.

## Gotchas

- `currentRepoMeta.analysis_count` is a snapshot from the last time
  `reposCache` was refreshed (home-view `loadRepos()`); it does **not**
  live-update while an analysis run is in progress on the currently open
  repo. This matches an existing, pre-existing limitation elsewhere in the
  UI (the header's `sh-analyzed` badge is updated separately via
  `_analyzePrefetch` after `_doAnalyze` completes) — not something this
  batch introduces, and acceptable per the locked decision, which explicitly
  said to use `analysis_count`/`has_case_study` "from the repo-list payload /
  currentRepoMeta".
- The regenerate endpoint is rate-limited server-side (`@limiter.limit("5/minute")`
  on `POST /case-study/regenerate`) — the new button doesn't add its own
  client-side throttling; a `429` from a rapid double-click would currently
  surface through the generic "Generation failed (HTTP {status})" message,
  same as any other non-2xx.

## Commits

- `feat: add Generate case study button when commits are analyzed but no narrative exists` — (SHA recorded after commit)
