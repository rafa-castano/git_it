# Feature Spec: Refresh All Repositories (Fetch New Commits Without Re-Pasting the URL)

**Status:** Draft
**Spec number:** 028
**Author:** Rafael Castaño
**Date:** 2026-07-07

---

## Summary

Add a single user-triggered "refresh all" action that, for **every** already-ingested
repository, does exactly what re-pasting that repository's URL into the home search box does
today for its commit corpus: `git fetch` on the bare cache **and** re-extract commit facts, so
any commits pushed upstream since the last ingest appear locally as **unanalyzed** commits,
ready for the existing `+ Analyze` action. It is a batch convenience over the existing
per-repository ingest flow (`RepositoryIngestionService.ingest`), not a new ingestion mechanism.

Crucially, refresh is the **free** half of the pipeline only — `git fetch` plus commit-fact
extraction, which cost no LLM calls. It never auto-analyzes: new commits land unanalyzed, and
running AI analysis over them stays a separate, explicit, paid step (`+ Analyze` /
`analyze-commits`). Refresh is user-triggered on demand; this spec explicitly rejects any
scheduler (cron / APScheduler / RQ). It is exposed on two surfaces (a CLI command and a home
dashboard button) and degrades gracefully per repository: a repo that fails to fetch is skipped
with its error surfaced, and never aborts the refresh of the others.

---

## Problem

To pull commits pushed since a repository was first ingested, the only path today is to
re-paste the repository's URL into the home search box. That triggers `POST /api/repos/ingest`
→ `_ingest_bg` → `RepositoryIngestionService.ingest(url)`, whose git gateway
(`SafeGitGateway.clone_or_fetch`) fetches into the existing bare cache and whose extractor
(`GitPythonCommitExtractor.extract_commits`) re-extracts commit facts; new commits are inserted,
existing ones reused (`CommitPersistenceResult(inserted, reused)`), and the new commits show up
in the Commits tab unanalyzed.

This works but is tedious and error-prone at scale: a user tracking several repositories must
find and re-paste each URL individually, one at a time, to see whether anything new landed.
There is no "check all my tracked repos for new commits" affordance. The information needed to
enumerate every tracked repository already exists —
`RepositoryListReader.list_repositories()` returns every known repository with its
`canonical_url` — so the batch action is a thin loop over the existing single-repo flow.

---

## Goals

1. A "refresh all" operation that enumerates every already-ingested repository via
   `RepositoryListReader.list_repositories()` and, for each, runs the same commit-corpus refresh
   the re-paste flow runs today: `git fetch` on the bare cache + re-extract commit facts, via the
   existing `RepositoryIngestionService.ingest(canonical_url)` path built by
   `build_repository_ingestion_service`.
2. **Depth is exactly re-paste's commit-corpus behavior.** New upstream commits are fetched and
   persisted as commit facts, appearing as **unanalyzed** commits in the Commits tab. Refresh
   performs no commit analysis and generates no case study.
3. **Cost separation stated explicitly.** `git fetch` + commit-fact extraction cost zero LLM
   calls. AI analysis of the newly fetched commits remains a separate, opt-in, paid step
   (`+ Analyze` in the dashboard, `analyze-commits` on the CLI). Refresh never spends LLM budget
   on commit analysis.
3a. **Refresh runs the free commit-corpus path ONLY — never the paid GitHub-evidence
   summarizers (LOCKED).** The current re-paste flow (`_ingest_bg`) does more than fetch+extract:
   after a `COMPLETED` ingest, and only when `GITHUB_TOKEN` is set, it also re-runs the
   discussion / release / advisory summarizers (`_fetch_and_store_discussion_evidence`,
   `_fetch_and_store_release_evidence`, `_fetch_and_store_advisory_evidence`), each of which
   **costs LLM calls**. Refresh-all deliberately diverges from full `_ingest_bg`: it invokes only
   the free commit-corpus refresh (`RepositoryIngestionService.ingest`, i.e. `git fetch` +
   commit-fact extraction, plus its free local side effects — `default_branch` and
   README/CHANGELOG re-read), and does **not** re-run any of the paid evidence summarizers. This
   is a locked user decision: "Refresh all" must stay free, so the paid GitHub-evidence refresh is
   excluded. Keeping that evidence current is done separately, via a full re-paste or a future
   dedicated action — never as a hidden cost of "Refresh all".
4. **Per-repository result reporting.** The action reports, per repository, how many new commits
   were found (e.g. "owner/repo: 3 new commits available"), derived from the existing
   `IngestionResult.commits_inserted` count, so the user knows where new analysis is worth
   running.
5. **Graceful per-repository degradation.** A repository that fails to fetch (network error,
   deleted/renamed upstream, auth failure) is skipped with its error surfaced (by safe message /
   exception type name), and the refresh continues with the remaining repositories — never
   aborting the whole batch on one failure.
6. **Two explicit surfaces:** a CLI command and a home-dashboard "Refresh all" button, both
   user-triggered.

---

## Non-goals

- **Any scheduler or background automation.** No cron, no APScheduler, no RQ/worker-queue,
  no interval polling, no "auto-refresh on a timer." Refresh happens only when the user
  explicitly triggers it. A scheduled/automatic refresh is a **deliberately deferred future
  decision** — one that would introduce a new runtime dependency and a new failure surface, and
  is therefore ADR-worthy if/when it is ever taken. It is out of scope here, on purpose.
- **Auto-analysis of newly fetched commits.** Refresh never runs `analyze-commits` or regenerates
  a case study. New commits stay unanalyzed until the user explicitly analyzes them.
- **Re-running the paid GitHub-evidence summarizers (LOCKED non-goal).** Refresh does not re-run
  the discussion / release / advisory summarizers that a full re-paste (`_ingest_bg`) triggers
  when `GITHUB_TOKEN` is set — those cost LLM calls, and refresh is locked as free. This is
  achieved naturally by calling `RepositoryIngestionService.ingest` (fetch + extract + free local
  side effects) directly, bypassing the `_ingest_bg` wrapper where the paid summarizer calls
  live. Keeping GitHub evidence current stays a separate, explicitly-paid action (a full re-paste
  today; a possible dedicated "refresh GitHub evidence" control in a future spec).
- **Adding new repositories.** Refresh only re-fetches repositories that are already ingested; it
  is not an "ingest these URLs" bulk-add. Adding a repository stays the existing paste-URL flow.
- **Selective / filtered refresh** (only repos older than N days, only a chosen subset). This
  spec is an all-or-nothing "refresh every tracked repo" action; a filtered variant is a
  separate future decision.
- **Concurrency / parallel fetch across repositories.** The first version refreshes repositories
  sequentially; whether to parallelize is deferred (each `git fetch` is I/O-bound but also
  touches a shared workspace, so parallelism is a real, separate decision).
- **Changing single-repo ingest behavior.** The existing paste-URL flow (`ingest_repo` /
  `_ingest_bg`) is unchanged; refresh-all reuses it.

---

## Users

- **Operator / learner tracking several repositories locally**: wants to see, in one action,
  which of their tracked repos have new commits, without re-pasting each URL — then chooses where
  to spend analysis budget.
- **Operator with a flaky or partially-unavailable set of repos**: wants one failing repo (e.g.
  an upstream that was deleted) to not block refreshing the rest.

---

## User stories

1. **As an operator tracking several repos**, I want one "Refresh all" action that fetches new
   commits for every tracked repository, so I don't have to re-paste each URL to discover
   what's new.
2. **As a cost-conscious operator**, I want refresh to be free — fetch and extract only — and to
   leave the new commits unanalyzed, so I decide where to spend analysis budget afterward.
3. **As an operator**, I want the refresh result to tell me how many new commits each repository
   gained, so I know which ones are worth analyzing.
4. **As an operator with one broken upstream**, I want that one repo's failure surfaced and
   skipped, while every other repo still refreshes.
5. **As an operator wary of surprise cost or hidden background jobs**, I want refresh to run only
   when I trigger it — never on a timer or at startup.

---

## Acceptance criteria

```gherkin
Feature: Refresh all repositories

  Background:
    Given three repositories have already been ingested
    And each has a recorded canonical_url

  Scenario: Refresh fetches new commits for every repository
    Given upstream has 3 new commits for repo A and 0 new for repos B and C
    When refresh-all runs
    Then each repository's bare cache is fetched and its commit facts re-extracted
    And repo A gains 3 newly inserted, unanalyzed commits
    And repos B and C gain 0 new commits
    And no commit analysis is run and no case study is generated for any repository

  Scenario: New commits appear as unanalyzed and analysis stays a separate step
    Given refresh-all has just fetched new commits for a repository
    When the Commits tab for that repository is viewed
    Then the new commits are listed with no analysis (category/summary empty)
    And they are analyzed only after the user runs + Analyze / analyze-commits

  Scenario: Per-repository result reporting
    When refresh-all completes
    Then the result reports, per repository, the number of new commits found
    And that count equals the ingestion result's commits_inserted for that repository

  Scenario: One repository failing does not abort the batch
    Given repo B's upstream is unreachable (network error or deleted upstream)
    When refresh-all runs
    Then repo B is reported as failed with a safe error indication
    And repos A and C are refreshed normally
    And the overall action still completes

  Scenario: No scheduler — refresh only on explicit trigger
    Given the application is running
    When no user triggers refresh
    Then no repository is fetched automatically
    And there is no timer, cron, or background job performing refresh

  Scenario: Refresh with no ingested repositories
    Given no repository has been ingested yet
    When refresh-all runs
    Then it reports that there is nothing to refresh
    And it exits successfully without error
```

---

## Domain concepts

- **`RepositoryListReader.list_repositories() -> list[RepositoryRecord]`**
  (`application/ports.py`; concrete `SqliteRepositoryListReader`/`PostgresRepositoryListReader`,
  built by `build_repository_list_reader`). Each `RepositoryRecord` carries
  `repository_id`, `canonical_url`, `status`, `commit_count`, `analysis_count`,
  `has_case_study` — the enumeration source for the batch, and `canonical_url` is the input each
  per-repo refresh needs.
- **`RepositoryIngestionService.ingest(raw_url) -> IngestionResult`**
  (`application/service.py`) — reused unchanged as the per-repository refresh primitive.
  Internally: `SafeGitGateway.clone_or_fetch(canonical_url)` performs the `git fetch` on the
  existing bare cache; `GitPythonCommitExtractor.extract_commits()` re-extracts; commit/file
  facts are upserted via `save_commit_facts`/`save_file_facts`, returning
  `CommitPersistenceResult(inserted, reused)`. Built per repository by
  `build_repository_ingestion_service(project_root=..., repository_id=...)`.
- **`IngestionResult`** (`application/service.py`) — `status` (`"COMPLETED"` or a
  `_FAILED_STATUSES` value), `commits_inserted`, `commits_reused`, `canonical_url`,
  `error_code`, `safe_message`. `commits_inserted` is the "N new commits found" number reported
  per repository; a `status` in the failure set is the per-repo "skipped with error" signal.
- **Refresh-all application service (new, proposed `RefreshAllService`)** — a thin orchestrator
  that enumerates repositories via the list reader, and for each calls the per-repository ingest
  primitive inside a try/except so one repository's failure is isolated (mirroring the
  best-effort posture already used by `_fetch_and_store_*` helpers in `api/routes/repos.py`),
  accumulating a per-repository result list (`repository_id`, `canonical_url`, `new_commits`,
  `status`/`error`). Depends only on the list-reader port and the ingest-service factory; exact
  names to be confirmed at build time.
- **Trigger points (new)**:
  - CLI: a new `refresh-all` subcommand registered in `main()` (`interfaces/cli.py`), alongside
    `ingest`/`analyze-commits`/`run`.
  - API: a new endpoint in `api/routes/repos.py` under `router` (prefix `/api/repos`), following
    the existing background-thread + progress-state pattern (`_ingest_bg` / `_analyze_bg` +
    `_analyze_progress` + status route) so the dashboard can poll progress.
  - Dashboard: a "Refresh all" button on the home view. The home grid is rendered by
    `renderRepoCards()` and repos are loaded by `loadRepos()` in `src/git_it/static/app.js`; the
    button belongs near the home controls in `src/git_it/static/index.html`
    (the `home-view` / add-repo area), calling the new endpoint and re-running `loadRepos()` /
    `renderRepoCards()` on completion.

---

## Inputs and outputs

- Input: none beyond the implicit "every already-ingested repository." No URL is pasted.
- `RepositoryListReader.list_repositories() -> list[RepositoryRecord]`.
- Per repository: `RepositoryIngestionService.ingest(canonical_url) -> IngestionResult`.
- Output: a per-repository result collection — for each repo, `canonical_url`, `new_commits`
  (`IngestionResult.commits_inserted`), and a completed/failed status (with a safe error
  indication on failure). Surfaced to CLI stdout and to the dashboard (list + counts, plus a
  progress/status endpoint for polling).

---

## Evidence requirements

- Refresh generates no interpreted claim; it only fetches and extracts commit facts. The "N new
  commits" figure reported per repository is a direct, evidence-backed count
  (`IngestionResult.commits_inserted`), not an inference.

---

## Failure modes

| Failure | Expected behavior |
|---|---|
| One repository's `git fetch` fails (network, deleted/renamed upstream, auth) | `IngestionResult.status` is a failure status; that repo is reported failed with its safe message / error code; the loop continues with the rest. Never aborts the batch. |
| A repository's URL no longer validates | Handled by the existing `ingest` URL-validation failure path (`RepositoryUrlValidationError` → failure `IngestionResult`); reported as a per-repo failure, batch continues. |
| No repositories ingested yet | Empty list from `list_repositories()`; "nothing to refresh" message; success exit. |
| Database not provisioned (API) | The existing `database_is_provisioned` gate returns the empty/appropriate response, consistent with `list_repos`. |
| Upstream reachable but has zero new commits | `commits_inserted == 0`; reported as "0 new commits"; success. |
| Unexpected exception during one repo's refresh | Caught per-repository, logged by `type(exc).__name__` only, that repo marked failed, batch continues (best-effort posture, same as the `_fetch_and_store_*` helpers). |

---

## Security considerations

- **Repository content stays untrusted input** (CODEX.md). Refresh fetches and extracts commit
  messages, author data, and file paths from public repositories — all treated as hostile input,
  exactly as the existing ingest flow already treats them. Refresh adds no new trust assumption;
  it reuses `RepositoryIngestionService` and its `SafeGitGateway` unchanged.
- **No code from analyzed repositories is executed** — refresh is `git fetch` + metadata
  extraction only, no build/run step, consistent with the security baseline.
- **Errors are surfaced safely** — per-repo failures are reported via the existing safe-message /
  exception-type-name conventions; raw exceptions (which could carry a fetch URL with an embedded
  token, or internal paths) are never surfaced to the user or logged in full.
- **No new credential and no new network surface** beyond the git remotes the existing ingest
  flow already contacts.

---

## Privacy considerations

- No new category of data is fetched or stored. Refresh re-runs the same public-repository commit
  extraction the initial ingest already performed — no additional exposure.

---

## Observability

- Per-repository: on success, a counts-only line (`repository_id` / `canonical_url` +
  `commits_inserted`); on failure, `_logger.warning("refresh failed: %s", type(exc).__name__,
  extra={"repository_id": ...})`, mirroring the existing `_ingest_bg` / `_fetch_and_store_*`
  logging.
- The dashboard action reuses the existing in-memory progress-state pattern (a lock-guarded dict
  like `_analyze_progress` in `api/routes/repos.py`), exposing overall running/done/total plus a
  per-repo result list, polled by a status endpoint just as analysis progress is today.
- No raw commit text or repository content is logged beyond what the existing ingest flow already
  logs.

---

## Tests required

### Unit tests (TDD, failing first)

- `tests/unit/test_refresh_all_service.py`:
  - enumeration: the service calls `list_repositories()` and invokes the per-repo ingest once
    per repository, with each repo's `canonical_url`;
  - result mapping: `IngestionResult.commits_inserted` is surfaced as each repo's `new_commits`;
  - per-repo failure isolation: one repo's ingest raising (or returning a failure status) marks
    that repo failed and still processes the remaining repos; failure logged by type name only;
  - empty case: no repositories → "nothing to refresh" result, no ingest calls;
  - no-analysis guarantee: the service never calls any analysis/narrative factory (assert the
    analysis path is not invoked).
  Uses injected fakes for the list reader and the ingest-service factory (mirrors the injection
  style in `test_analyze_commits_cli.py` / the repos route tests).
- `tests/unit/test_refresh_all_cli.py`: new `refresh-all` subcommand — prints a per-repo summary
  with new-commit counts, reports a failed repo without aborting, handles the empty case, returns
  success; injected factories so no real git/network is touched.
- `tests/unit/test_repos_refresh_all_endpoint.py` (or extend the repos route tests): the new
  endpoint starts the background refresh, exposes progress/status, isolates a per-repo failure,
  and honors the `database_is_provisioned` gate.
- `tests/integration/test_refresh_all_roundtrip.py`: with a real SQLite backend and two seeded
  repositories (one whose fake gateway "fetches" new commits, one whose fake gateway raises), run
  refresh-all and assert the first gains unanalyzed commit-fact rows, the second is reported
  failed, and neither has any new commit-analysis rows (the no-auto-analyze guarantee at the
  storage layer).

### TDD order

Refresh-all service (enumeration + isolation + result mapping + no-analysis guarantee, with
fakes) → CLI command → API endpoint + progress/status → dashboard button. Same layering the
module already uses.

---

## Evaluation required

No LLM-output eval is needed — refresh produces no interpreted claim, only fetched commit facts.
The properties that matter (correct enumeration, per-repo failure isolation, accurate new-commit
counts, and the no-auto-analyze guarantee) are deterministic and covered by the unit and
integration tests above.

---

## Documentation impact

- A future build batch creates `docs/progress/{area}/batch-{N}-refresh-all-repositories.md`
  (area: `ingestion` or `pipeline`) and adds the entry to `docs/progress/README.md` in the same
  commit.
- `README.md` should gain a short note on the "Refresh all" action as the supported way to pull
  new commits for tracked repositories without re-pasting each URL (and that new commits arrive
  unanalyzed, analysis being a separate step).
- `docs/architecture.md` Roadmap and `docs/specs/index.md` get this spec's row (added by this
  change).

---

## ADR impact

**Assessment: no new ADR needed for the refresh action itself.** Refresh-all is a batch
convenience over the already-decided `RepositoryIngestionService.ingest` flow — it introduces no
new ingestion mechanism, no new dependency, no new data model, and no new boundary. It reuses the
existing list reader, ingest service, git gateway, and the best-effort per-item isolation posture
already established. That is the same "mechanical extension of an existing pattern" reasoning
spec 026 used to conclude "no new ADR."

**However**, the *deliberately rejected* scheduler is ADR-worthy the day it is reconsidered.
Introducing automatic/scheduled refresh (APScheduler/cron/RQ) would add a new runtime dependency,
a new always-on failure surface, and new cost-control questions — exactly the kind of decision
`docs/adr/` exists to record. This spec locks "no scheduler" as a Non-goal and flags that a future
"yes, schedule it" decision must be accompanied by its own ADR. Note also the existing
`docs/adr/010-local-first-mvp-accepted-limitations.md` frames the local-first posture this action
stays within.

---

## Open questions

1. **Exact CLI command name.** Proposed `git-it refresh-all` (reads naturally as an all-repos
   verb; distinct from the single-repo `ingest`). Not locked — `refresh-all` vs. `refresh` (with
   an implicit "all") vs. `fetch-all` should be confirmed against the help-output wording.
2. **Best-effort GitHub-token evidence summarizers during refresh — RESOLVED (LOCKED).**
   Re-pasting a URL today runs `_ingest_bg`, which — after a `COMPLETED` ingest and only when
   `GITHUB_TOKEN` is set — also re-runs the discussion / release / advisory summarizers
   (`_fetch_and_store_discussion_evidence`, `_fetch_and_store_release_evidence`,
   `_fetch_and_store_advisory_evidence`), all of which cost LLM calls. **User decision: refresh-all
   runs the commit-corpus refresh ONLY (`RepositoryIngestionService.ingest`) and does NOT re-run
   the paid evidence summarizers**, so "Refresh all" stays free (see Goal #3a and the locked
   non-goal). This is a deliberate divergence from full `_ingest_bg`, achieved by calling
   `svc.ingest` directly and bypassing the `_ingest_bg` wrapper. Sub-question resolved: the free,
   non-LLM local side effects of `ingest` (`default_branch` refresh and README/CHANGELOG re-read)
   are kept, since they cost nothing; the single non-LLM `_fetch_and_store_repo_metadata` GitHub
   API call lives in the `_ingest_bg` wrapper and is therefore also excluded by the
   call-`ingest`-directly approach — acceptable, since stars/languages metadata is not the point
   of a commit refresh and can be refreshed via a full re-paste.
3. **Sequential vs. concurrent fetch.** Proposed sequential for the first version (simpler, avoids
   shared-workspace contention). Parallelizing across repositories is deferred.
4. **API surface shape.** Whether the endpoint is `POST /api/repos/refresh-all` with a companion
   status route (mirroring analyze/estimate/status), and whether it returns the per-repo result
   list synchronously or only via the status poll. The `_analyze_bg` + progress + status trio is
   the proposed template.
5. **Dashboard button placement and result display.** Proposed a "Refresh all" button in the home
   view (`src/git_it/static/index.html` add-repo/controls area; wired in
   `src/git_it/static/app.js` near `renderRepoCards()`/`loadRepos()`), with a per-repo
   "N new commits" summary after completion. Exact placement/label not locked.
6. **Does refresh update `default_branch` / project docs?** `RepositoryIngestionService.ingest`
   also refreshes the default branch and README/CHANGELOG excerpt (both token-independent, local,
   free). Since refresh reuses `ingest` unchanged, these are updated as a free side effect —
   confirm this is desired (it almost certainly is, and it is free) rather than a surprise.

---

## Out of scope

- Any implementation (refresh-all service, CLI command, API endpoint, dashboard button, tests) —
  deferred to a future build batch.
- Any scheduler / cron / APScheduler / RQ automatic refresh — explicit non-goal, ADR-worthy if
  ever reconsidered.
- Auto-analysis or case-study regeneration of newly fetched commits — analysis stays a separate,
  opt-in, paid step.
- Bulk-adding new repositories, filtered/selective refresh, and concurrent multi-repo fetch.
