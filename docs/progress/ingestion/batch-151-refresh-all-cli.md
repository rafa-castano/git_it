## Batch 151 — `refresh-all` CLI command (spec 028, slice 2)

### Goal

Expose `RefreshAllService` (batch 150) on a CLI surface: `git-it refresh-all`, with no URL
argument — it refreshes every already-ingested repository's commit corpus in one shot.
Slice 2 of spec 028's build order (refresh-all service → **CLI command** → API endpoint +
progress → dashboard button); the API endpoint and dashboard button are out of scope here
and land in batches 152/153.

### Why

Slice 1 built the orchestrator; nothing could trigger it yet. This batch gives operators a
"refresh all my tracked repos" affordance without re-pasting each URL, exactly spec 028's
core user story — and, unlike `analyze-commits`/`backfill-embeddings`, needs no budget
guardrail because refresh is free (no LLM calls).

### What was added

**`interfaces/cli.py`**
- New protocols: `RefreshAllServiceProtocol` (`refresh_all() -> RefreshAllResult`) and
  `RefreshAllFactory` (`__call__(*, project_root: Path) -> RefreshAllServiceProtocol`),
  following the exact `BackfillService`/`BackfillFactory` shape already used for
  `backfill-embeddings`.
- `main()` gained a `refresh_all_factory: RefreshAllFactory = build_refresh_all_service`
  keyword parameter, defaulting straight to the real composition factory (no extra
  indirection needed since `build_refresh_all_service(*, project_root)` already matches the
  protocol signature exactly — no wrapper function required, unlike
  `_default_backfill_factory`'s no-key special casing).
- New `refresh-all` subparser registered in `main()` alongside the others: **no positional
  argument** (it refreshes every ingested repository, not one URL).
- `_run_refresh_all(*, project_root, refresh_all_factory)`: builds the service, calls
  `refresh_all()`, prints the result, always returns 0 (per-repo failures are reported in
  output, never fatal — matches spec 028's graceful-degradation posture; there is no
  budget-confirmation branch to abort on, unlike `analyze-commits`/`backfill-embeddings`).
- `_print_refresh_all_result(result)`:
  - `result.nothing_to_refresh` → prints "No repositories to refresh — ingest one first."
    and returns.
  - Otherwise, for each `RepositoryRefreshResult`: on `"completed"`, prints
    `"{owner/repo}: {new_commits} new commit(s)"`; on `"failed"`, prints
    `"{owner/repo}: failed ({safe_message or error_code or 'unknown error'})"` — safe text
    only, mirroring the existing `_print_ingestion_result`'s failure branch.
  - Ends with a totals line: `"Refreshed {refreshed_count} repositories, {total_new_commits}
    new commits, {failed_count} failed"`.
  - Reuses the existing inline `canonical_url.removeprefix("https://github.com/")` idiom
    from `_print_ingestion_result` (no shared helper existed to extract; not introduced
    speculatively since only two call sites need it).

### Real symbols grounded on

- `RefreshAllService.refresh_all() -> RefreshAllResult` and `RepositoryRefreshResult`
  (`application/refresh_all_service.py`, batch 150) — confirmed field names
  (`repository_id`, `canonical_url`, `status`, `new_commits`, `error_code`, `safe_message`)
  and the `RefreshAllResult.nothing_to_refresh` property before writing the printer.
- `build_refresh_all_service(*, project_root: Path) -> RefreshAllService`
  (`composition.py`, batch 150) — confirmed it takes only `project_root` (no
  `repository_id`; it enumerates all repositories itself via `build_repository_list_reader`
  internally), so it plugs directly into `main()`'s default-parameter slot with zero
  wrapping, unlike `backfill_factory`.
- `main()`'s existing factory-injection pattern (`service_factory`, `backfill_factory`,
  etc.) and subparser registration style (`subparsers.add_parser(...)` + `args.command ==
  "..."` dispatch) in `interfaces/cli.py` — followed exactly for `refresh-all`.
- `_print_ingestion_result`'s `canonical_url.removeprefix("https://github.com/")` idiom —
  reused inline for the owner/repo display string.

### Tests added

`tests/unit/test_refresh_all_cli.py` (4 tests, new file, mirrors
`test_backfill_embeddings_cli.py`'s injection style — a hand-rolled `FakeRefreshAllService`
wrapping a real `RefreshAllResult`/`RepositoryRefreshResult`, no real git/network/DB):
- `test_refresh_all_empty_prints_nothing_to_refresh_and_exits_zero` — empty result → "No
  repositories to refresh" message, exit 0, service called once.
- `test_refresh_all_reports_per_repository_new_commits_and_totals` — two completed repos →
  each repo's new-commit count printed plus a totals line.
- `test_refresh_all_reports_failed_repository_without_aborting` — one completed + one failed
  repo → both repos reported, failed repo's safe message shown, exit still 0.
- `test_refresh_all_returns_zero_on_normal_run` — exit code is always 0.

All 4 were RED first (`main()` raised `TypeError: main() got an unexpected keyword argument
'refresh_all_factory'` — no `refresh-all` subcommand or factory parameter existed yet),
confirmed failing for the right reason, then GREEN after implementation.

Full suite: **1154 passed, 33 skipped** (no regressions; +4 new tests over batch 150's
baseline).

### Gotchas

- First GREEN attempt still failed one test: the empty-case message text is "No
  repositories to refresh — ingest one first." (per this batch's brief), which does not
  contain the literal substring "nothing to refresh" my first test assertion checked for —
  fixed the test assertion to match the actual required wording rather than change the
  message.
- `ruff check .` / `ruff format --check .` both print a pre-existing, unrelated `Acceso
  denegado (os error 5)` warning while walking `tmp/pytest-of-*` / `.claude/worktrees/` —
  already documented in batch 150's gotchas; every check still reports `All checks passed!`
  / `... files already formatted` with exit 0.
- `mypy tests/unit/test_refresh_all_cli.py` run **in isolation** (a single test file, no
  src file in the same invocation) reports `import-untyped` errors ("module is installed,
  but missing library stubs or py.typed marker") for its `git_it.*` imports. Verified this
  is a pre-existing, project-wide mypy package-root-resolution quirk, **not** specific to
  this new file: the same bare-invocation error reproduces identically for the
  already-merged `tests/unit/test_backfill_embeddings_cli.py`, and running `mypy tests/`
  (the whole directory) reproduces it across 121 files project-wide. Including any one
  `src/` file in the same mypy invocation (e.g. `mypy tests/unit/test_refresh_all_cli.py
  tests/unit/test_backfill_embeddings_cli.py src/git_it/repository_ingestion/interfaces/cli.py`)
  resolves cleanly with **0 errors**, confirming the new test file itself is mypy-clean and
  the failure mode is purely an artifact of how mypy resolves the `git_it` package root when
  given no anchoring first-party file. `mypy src/` (this batch's other required gate) passes
  clean on its own. `mypy .` from the repo root also fails, but with an unrelated
  `PermissionError: [WinError 5] Acceso denegado: 'tmp\pytest-of-rcastano'` while walking a
  stray temp directory — the same environment noise as the ruff warning above, not a code
  issue.
- `tests/unit/test_api_static.py` showed as modified in `git status` with no functional diff
  (pre-existing line-ending noise per this batch's brief) — left untouched and unstaged.
- Confirmed no `api/routes/`, `static/`, `application/`, or `composition.py` files were
  touched — this batch is scoped strictly to the CLI interface layer, per spec 028's build
  order (refresh-all service → **CLI command** → API endpoint → dashboard button).

### Commits

- Not committed — per this batch's instructions, changes are left uncommitted for review.
