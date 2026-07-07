## Batch 146 — `backfill-embeddings` CLI command (spec 027, slice 2)

### Goal

Expose `EmbeddingBackfillService` (batch 145) on a CLI surface: `git-it backfill-embeddings
<repo-url>`, honoring the same budget-confirmation guardrail (batch 38) that
`analyze-commits`/`run` already use, and behaving as a clean no-op when no OpenAI key is
configured. Slice 2 of spec 027's build order (backfill service → **CLI command** → API
endpoint + progress → dashboard control); the API endpoint and dashboard control are out
of scope here and land in batch 147.

### Why

Slice 1 built the orchestrator; nothing could trigger it yet. This batch gives operators
who added `OPENAI_API_KEY` after already analyzing a repository a way to backfill
embeddings for that existing corpus without re-running (and re-paying for) commit
analysis — spec 027's core user story.

### What was added

**`interfaces/cli.py`**
- New protocols: `BackfillService` (`estimate_backfill_calls(repository_id) -> int`,
  `backfill(repository_id) -> EmbeddingBackfillResult`) and `BackfillFactory`
  (`__call__(*, project_root: Path) -> BackfillService | None`).
- `_default_backfill_factory(*, project_root)` — **key discovery from grounding on real
  code**: `build_embedding_backfill_service` (batch 145) never returns `None`; it always
  returns a service instance whose *internal* `_embedder` is `None` without a key. That
  collapses two distinct CLI-visible states (no key vs. "everything already embedded",
  both signaled by an internal `None`/zero) into one signal, but spec 027's acceptance
  criteria and this batch's test list require different user-facing messages for each. The
  default factory resolves this without touching the service or its composition factory
  (both out of scope per this batch's instructions): it calls `build_embedding_client()`
  directly — the same public "single source of truth for RAG availability" function every
  other call site already checks — and returns `None` itself when no key is configured,
  otherwise delegating to `build_embedding_backfill_service`. The CLI layer's own factory
  contract (`BackfillFactory` returning `BackfillService | None`) is therefore the
  no-key signal, not the service internals.
- `_run_backfill_embeddings(...)`: resolves `repository_id` via the existing
  `repository_id_for_url` (same mechanism `analyze-commits`/`commits` use); if the factory
  returns `None`, prints an "OPENAI_API_KEY is not configured..." message and exits 0
  (never an error); otherwise calls `estimate_backfill_calls`, prints "nothing to
  backfill" and exits 0 if it's 0; otherwise mirrors `_run_analyze_commits`'s exact budget
  guardrail shape (`estimate > budget_threshold and not yes` gates a call to
  `budget_confirm_fn`, aborting with exit 1 and an "Aborted." message on decline — the
  same exit code `analyze-commits`/`run` already use on decline); on proceed (confirmed,
  `--yes`, or under threshold), calls `backfill(repository_id)` and prints a one-line
  summary via `_print_backfill_result` (embedded / already-present / failed counts from
  `EmbeddingBackfillResult`).
- New `backfill-embeddings` subparser registered in `main()` alongside the others:
  `repository_url` positional + `--yes` flag (same shape as `analyze-commits`'s `--yes`).
  `main()` gained a `backfill_factory: BackfillFactory = _default_backfill_factory`
  keyword parameter, following the existing factory-injection pattern for every other
  command.

### Real symbols grounded on

- `repository_id_for_url(raw_url)` (`interfaces/cli.py`) — the exact resolver every other
  command uses; reused unchanged.
- `_default_budget_confirm(count) -> bool` and `_DEFAULT_BUDGET_THRESHOLD = 50`
  (`interfaces/cli.py`) — reused unchanged as the default `budget_confirm_fn`/
  `budget_threshold` for the new command (via `main()`'s existing defaults).
- `--yes` wiring — mirrors `analyze_commits_parser`'s `action="store_true", default=False`.
- `build_embedding_backfill_service(*, project_root: Path) -> EmbeddingBackfillService`
  (`composition.py`) — confirmed it takes only `project_root` (no `repository_id`; that's
  passed per-call to the service's own methods) and **always returns a service**, never
  `None` — the deviation from this batch's initial assumption, resolved as described above
  by having `_default_backfill_factory` check `build_embedding_client()` itself rather than
  relying on the composition factory to signal unavailability.

### Tests added

`tests/unit/test_backfill_embeddings_cli.py` (7 tests, new file, mirrors
`test_analyze_commits_cli.py`'s injection style — a hand-rolled `FakeBackfillService`
tracking `estimate_calls`/`backfill_calls`, no real DB/network/LLM):
- `test_backfill_embeddings_no_key_prints_message_and_exits_zero` — factory returns `None`
  → "OPENAI_API_KEY" message, exit 0.
- `test_backfill_embeddings_zero_estimate_prints_nothing_to_backfill` — estimate 0 →
  "nothing to backfill" message, exit 0, `backfill()` never called.
- `test_backfill_embeddings_aborts_when_budget_exceeded_and_not_confirmed` — estimate above
  threshold, confirm declines → exit 1, `backfill()` never called.
- `test_backfill_embeddings_yes_flag_skips_budget_confirmation` — `--yes` above threshold →
  confirm never called, `backfill()` called once.
- `test_backfill_embeddings_proceeds_when_budget_confirmed` — confirm accepts → `backfill()`
  called once.
- `test_backfill_embeddings_no_confirmation_when_under_threshold` — estimate below
  threshold → confirm never called, `backfill()` still called.
- `test_backfill_embeddings_prints_result_summary` — printed output reflects
  `EmbeddingBackfillResult`'s `embedded`/`already_present`/`failed` counts.

All 7 were RED first (`main()` didn't accept `backfill_factory` and no `backfill-embeddings`
subcommand existed — `SystemExit`/`TypeError` failures), confirmed failing for the right
reason, then GREEN after implementation.

Full suite: **1117 passed, 33 skipped** (was 1110 passed / 33 skipped before this batch; +7
new tests, no regressions).

### Gotchas

- `ruff format --check` reformatted one line in the new test file (a dataclass default-arg
  expression); `ruff format` (applied in place) fixed it, no functional change.
- The batch brief assumed `build_embedding_backfill_service` might return `None` directly
  for the no-key case; reading the real batch-145 code showed it always returns a service
  instance with an internal `None` embedder instead. Rather than add a public
  "has-embedder" property to `EmbeddingBackfillService` (a change to the service, out of
  scope without a genuine bug), the default CLI factory independently calls the existing
  public `build_embedding_client()` gate — the same function every other RAG call site
  already checks — keeping the no-key signal at the CLI's own factory boundary
  (`BackfillFactory -> BackfillService | None`) without touching `embedding_backfill_service.py`
  or `composition.py`.
- Did not touch `api/routes/` or `static/` — out of scope for this slice, deferred to
  batch 147 per spec 027's build order.

### Commits

- (staged, not committed by this batch — orchestrator will review and commit)
