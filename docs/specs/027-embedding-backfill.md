# Feature Spec: Embedding Backfill for Previously-Analyzed Evidence

**Status:** Draft
**Spec number:** 027
**Author:** Rafael Castaño
**Date:** 2026-07-07

---

## Summary

Add an explicit, user-triggered action that computes embedding vectors for evidence that
was analyzed and persisted **before** `OPENAI_API_KEY` was configured. Today embeddings are
only ever computed *live*, inline with analysis: `CommitAnalysisService` embeds each fresh
`CommitAnalysis` through `EmbeddingService.embed_commit_analysis`, and the discussion-ingest
path in `api/routes/repos.py` (`_fetch_and_store_discussion_evidence`) embeds each fresh
`DiscussionEvidence` through `EmbeddingService.embed_discussion_evidence`. Anything analyzed
while no OpenAI key was present has a persisted `commit_analyses` / `discussion_evidence` row
but **no** matching `embedding_vectors` row, and nothing ever fills that gap — a limitation the
README documents explicitly (lines 75 and 149: "old analyses are not backfilled automatically").

This spec closes that gap with a backfill that enumerates already-stored commit analyses and
discussion evidence, computes embeddings only for the items that have no embedding yet, and
persists them through the existing `EmbeddingWriter.save_embeddings` upsert — reusing the
existing budget-confirmation guardrail (batch 38) and the existing per-item failure isolation
posture of `EmbeddingService`. It is exposed on two surfaces (a CLI command and a per-repo
dashboard control) and is a clean no-op when no OpenAI key is configured. It embeds **both**
`commit_analyses` and `discussion_evidence` — full parity with what the live analysis pipeline
embeds today — and nothing else.

---

## Problem

Git It's semantic-search feature (spec 023) works only over content that was embedded at the
moment it was analyzed. `build_embedding_client()` is the single source of truth for "is the
RAG feature available": it returns `None` unless `OPENAI_API_KEY` is set, and every embedding
call site checks that return value and skips silently when it is `None`.

The realistic operator sequence is: analyze a repository first (with only `ANTHROPIC_API_KEY`
set, since commit analysis does not need OpenAI), discover semantic Ask returns nothing, *then*
add `OPENAI_API_KEY`. At that point the commit analyses and discussion evidence already exist,
but their embeddings never do — the live embedding hooks only fire on *new* analysis, and
re-running analysis would re-spend LLM budget on commit analysis just to trigger the embedding
side effect. There is no path today to compute embeddings for already-analyzed evidence without
re-doing (and re-paying for) the analysis itself. The README currently tells the user the only
workaround is to re-analyze, which is both expensive and misleading (re-analysis of an already
analyzed commit is skipped, so the embedding side effect may not even fire).

---

## Goals

1. A backfill operation that, for one repository, computes embeddings for every already-stored
   `commit_analyses` and `discussion_evidence` item that does **not** already have a matching
   `embedding_vectors` row, and persists them via the existing
   `EmbeddingWriter.save_embeddings` upsert. Full parity with the live pipeline: both source
   types, nothing more.
2. **Idempotent by construction.** The embedding store's primary key is
   `(repository_id, source_type, source_id)` with `ON CONFLICT ... DO UPDATE` upsert. The
   backfill computes and writes embeddings **only** for items whose `(source_type, source_id)`
   is absent from the set returned by `EmbeddingReader.get_all_embeddings(repository_id)`.
   Re-running the backfill after a completed run performs zero embedding calls and never
   duplicates or corrupts an existing row.
3. **Reuses the existing budget guardrail** (batch 38). Before spending, the backfill computes
   how many embedding calls it will make (the count of items missing an embedding), surfaces
   that number, and requires confirmation — honoring the same `--yes` / non-interactive
   escape hatch and the same confirmation-callback mechanism (`_default_budget_confirm`,
   `_DEFAULT_BUDGET_THRESHOLD`) already used by `analyze-commits` and `run`.
4. **No key → clean no-op.** When `build_embedding_client()` returns `None` (no
   `OPENAI_API_KEY`), the backfill performs no work, writes nothing, and reports an
   explanatory message. It is never an error.
5. **Two explicit surfaces, never auto-triggered.** A CLI command and a per-repo dashboard
   control, both requiring deliberate user action. The backfill is never fired automatically
   on key presence or on startup (see Non-goals for why).
6. **Per-item failure isolation identical to `EmbeddingService`'s existing posture:** a single
   item's embedding failure (rate limit, network error, malformed response) returns `None` for
   that item, is logged by `type(exc).__name__` only, and never aborts the batch — the exact
   behavior `EmbeddingService._embed` already implements.

---

## Non-goals

- **Auto-triggering the backfill when a key appears.** The application persists no "an OpenAI
  key just became available" state. Detecting the transition automatically would mean either
  (a) attempting a backfill on every process boot (wasteful, and surprising LLM spend the
  operator did not ask for), or (b) introducing and maintaining a fragile "key seen" flag with
  its own invalidation problems. This spec deliberately keeps the trigger a manual, explicit
  user action on both surfaces. Auto-detection is an explicit non-goal.
- **Embedding releases or security advisories.** `ReleaseEvidence` and `AdvisoryEvidence`
  (spec 026) are not embedded by anything today — spec 026 lists RAG embedding as an explicit
  non-goal, and no `EmbeddedChunk.source_type` literal exists for them. Backfilling them would
  require new source-type literals and new `EmbeddingService` methods; that is out of scope here
  and stays consistent with spec 026's own boundary. Backfill parity is with the **live
  pipeline**, which embeds only `commit_analysis` and `discussion_evidence`.
- **Re-embedding already-embedded items** (model upgrades, re-vectorization). The backfill only
  fills gaps; it does not re-compute embeddings that already exist. A future "re-embed with a
  new model" operation is a separate decision.
- **Backfilling other embeddable summary fields.** Only `CommitAnalysis.summary` is embedded
  (never `summary_beginner`/`summary_expert`) and only `DiscussionEvidence.summary` — the two
  locked decisions from spec 023. The backfill matches those exactly and introduces no new
  embedded text.
- **A background job / scheduler.** The backfill runs synchronously in the CLI, and in a
  background thread for the dashboard control mirroring the existing `_analyze_bg` progress
  pattern — not on any cron/APScheduler/queue.
- **Changing the live embedding hooks.** The analysis-time and discussion-ingest-time embedding
  computation is unchanged; this spec only adds a catch-up path for what those hooks missed.

---

## Users

- **Operator / learner running Git It locally**: added `OPENAI_API_KEY` after already analyzing
  one or more repositories, and wants semantic Ask to work for that existing corpus without
  paying to re-analyze.
- **Operator without an OpenAI key**: unaffected — the control is either hidden/no-op, and
  every other feature works exactly as today.

---

## User stories

1. **As an operator who added `OPENAI_API_KEY` after analyzing a repo**, I want to run one
   command (or click one button) that computes embeddings for that repo's existing analyses and
   discussion evidence, so semantic Ask starts working for it — without re-running (and
   re-paying for) commit analysis.
2. **As a cost-conscious operator**, before the backfill spends anything I want to see how many
   embedding calls it will make and confirm, exactly like `analyze-commits` already does — with
   a `--yes` flag to skip the prompt in scripts.
3. **As an operator running the backfill twice**, I want the second run to be a no-op (zero
   calls, zero changes), because everything is already embedded.
4. **As an operator without an OpenAI key**, I want the backfill to tell me plainly that
   semantic search is unavailable without a key, rather than erroring.
5. **As an operator where one item fails to embed** (transient rate limit), I want that one item
   skipped and every other item still embedded, with the failure logged by type name only.

---

## Acceptance criteria

```gherkin
Feature: Embedding backfill for previously-analyzed evidence

  Background:
    Given a repository has stored commit_analyses and discussion_evidence rows
    And some of those items have no matching embedding_vectors row

  Scenario: Backfill computes embeddings only for items missing them
    Given OPENAI_API_KEY is set
    And 8 commit analyses and 3 discussion-evidence items exist
    And 2 of those commit analyses already have an embedding_vectors row
    When the backfill runs for the repository
    Then exactly 9 embeddings are computed (6 commit analyses + 3 discussion evidence)
    And each new embedding is persisted with source_type "commit_analysis" keyed by the
      commit_sha, or source_type "discussion_evidence" keyed by the discussion_url
    And the 2 already-embedded items are neither re-computed nor duplicated

  Scenario: Backfill is idempotent on re-run
    Given OPENAI_API_KEY is set
    And a prior backfill has already embedded every eligible item for the repository
    When the backfill runs again for the same repository
    Then zero embedding calls are made
    And no embedding_vectors row is added, changed, or duplicated

  Scenario: Budget confirmation is required before spending
    Given OPENAI_API_KEY is set
    And 120 items are missing embeddings, above the budget threshold
    When the backfill runs without the --yes flag in an interactive session
    Then the number of planned embedding calls is shown
    And the backfill proceeds only if the user confirms
    And it aborts without spending if the user declines

  Scenario: --yes skips the confirmation prompt
    Given OPENAI_API_KEY is set
    And the number of items missing embeddings is above the budget threshold
    When the backfill runs with --yes
    Then no prompt is shown
    And the backfill proceeds directly

  Scenario: No OpenAI key is a clean no-op
    Given OPENAI_API_KEY is not set
    When the backfill runs for the repository
    Then build_embedding_client() returns None
    And no embedding call is made and nothing is persisted
    And an explanatory message states semantic search needs OPENAI_API_KEY
    And the exit is success, not an error

  Scenario: Per-item failure isolation
    Given OPENAI_API_KEY is set
    And the embedding call fails for exactly one commit analysis among several
    When the backfill runs
    Then that one item has no persisted embedding_vectors row
    And every other eligible item is embedded and persisted normally
    And the failure is logged with only its exception type name

  Scenario: Dashboard control visibility
    Given OPENAI_API_KEY is configured
    And a repository has at least one analyzed item missing an embedding
    When the home dashboard renders that repository's card
    Then a backfill control is shown for that repository
    And it is absent when either no key is configured or nothing is missing an embedding
```

---

## Domain concepts

- **Backfill target set (derived, not a new persisted entity)**: the set of
  `(source_type, source_id)` pairs that *should* have an embedding but do not. Computed by
  enumerating:
  - already-stored commit analyses via `CommitAnalysisReader.list_analyses(repository_id,
    limit=None) -> list[CommitAnalysis]` (each contributes `("commit_analysis",
    analysis.commit_sha)`), and
  - already-stored discussion evidence via
    `DiscussionEvidenceReader.get_discussion_evidence(repository_id) -> list[DiscussionEvidence]`
    (each contributes `("discussion_evidence", evidence.discussion_url)`),
  then subtracting the set of `(chunk.source_type, chunk.source_id)` already present in
  `EmbeddingReader.get_all_embeddings(repository_id) -> list[EmbeddedChunk]`. The subtraction is
  the idempotency mechanism.
- **`source_id` keys (locked, must match the live pipeline exactly)**: for `commit_analysis`,
  `source_id` is `CommitAnalysis.commit_sha`; for `discussion_evidence`, `source_id` is
  `DiscussionEvidence.discussion_url` (the full citation-ready URL, **not** the bare
  `discussion_id`). These match `EmbeddingService.embed_commit_analysis` /
  `.embed_discussion_evidence` so a backfilled row and a live-computed row for the same item are
  the same primary key and upsert cleanly.
- **`EmbeddingService`** (`application/embedding_service.py`) — reused unchanged. The backfill
  calls `embed_commit_analysis(repository_id, analysis)` and
  `embed_discussion_evidence(repository_id, evidence)`, each returning `EmbeddedChunk | None`,
  and collects the non-`None` results for `save_embeddings`. Its existing `_embed`
  catch/log-type-name/return-`None` posture is the per-item failure isolation this spec
  requires — no new isolation logic is written.
- **Backfill application service (new, proposed `EmbeddingBackfillService`)** — a thin
  orchestrator that: reads the two evidence readers, reads existing embeddings, computes the
  missing set, exposes a count (`estimate_backfill_calls`, mirroring the *shape* of
  `estimate_llm_calls`), and on execution computes + persists embeddings for the missing set
  with per-item isolation. Depends only on ports
  (`CommitAnalysisReader`, `DiscussionEvidenceReader`, `EmbeddingReader`, `EmbeddingWriter`,
  and an `EmbeddingAnalyzer`-shaped embedder), never on concrete infrastructure — consistent
  with the hexagonal boundary the rest of the module keeps. Exact class/method names to be
  confirmed at build time.
- **Composition factory (new, proposed `build_embedding_backfill_service`)** —
  `src/git_it/repository_ingestion/composition.py`. Backend-aware via `_get_db_backend()`,
  wires `build_commit_analysis_reader`, `build_discussion_evidence_store`,
  `build_embedding_store` (which implements both `EmbeddingReader` and `EmbeddingWriter`), and
  `build_embedding_client()`. Returns something that no-ops when the client is `None`.

---

## Inputs and outputs

- Input: a repository identifier (derived from the pasted URL on the CLI via
  `repository_id_for_url`, or the `{repository_id}` path param on the API).
- `CommitAnalysisReader.list_analyses(repository_id, *, limit=None) -> list[CommitAnalysis]`
  (`application/ports.py`; concrete `SqliteCommitAnalysisStore`/`PostgresCommitAnalysisStore`,
  built by `build_commit_analysis_reader`).
- `DiscussionEvidenceReader.get_discussion_evidence(repository_id) -> list[DiscussionEvidence]`
  (`application/ports.py`; concrete `SqliteDiscussionEvidenceStore`/
  `PostgresDiscussionEvidenceStore`, built by `build_discussion_evidence_store`).
- `EmbeddingReader.get_all_embeddings(repository_id) -> list[EmbeddedChunk]` and
  `EmbeddingWriter.save_embeddings(repository_id, items: list[EmbeddedChunk]) -> None`
  (`application/ports.py`; concrete `SqliteEmbeddingStore`/`PostgresEmbeddingStore`, table
  `embedding_vectors`, PK `(repository_id, source_type, source_id)`, built by
  `build_embedding_store`).
- `EmbeddingService.embed_commit_analysis(repository_id, analysis) -> EmbeddedChunk | None`,
  `.embed_discussion_evidence(repository_id, evidence) -> EmbeddedChunk | None`.
- `build_embedding_client() -> LiteLLMEmbeddingClient | None` (`None` without `OPENAI_API_KEY`).
- Output: a count of items embedded (and a count skipped-because-failed), surfaced to the CLI
  stdout / the dashboard progress state. No new persisted entity beyond the `embedding_vectors`
  rows the existing writer produces.

---

## Evidence requirements

- The backfill produces no user-facing educational claim itself; it only computes vectors over
  **already-validated** summary text (`CommitAnalysis.summary` /
  `DiscussionEvidence.summary`) — never raw commit/diff or raw discussion text (the spec 023
  boundary is preserved because the backfill reuses `EmbeddingService`, which only ever receives
  the validated summary).
- Each backfilled `EmbeddedChunk` carries the same `source_id` the live pipeline would have used,
  so downstream `SemanticSearchService` results built from a backfilled embedding remain
  citation-linked identically to live-embedded ones (the `discussion_url` source_id is the
  citation-ready reference).

---

## Failure modes

| Failure | Expected behavior |
|---|---|
| `OPENAI_API_KEY` unset (`build_embedding_client()` is `None`) | No embedding call; nothing persisted; explanatory message; success exit. Never an error. |
| Repository has no analyses and no discussion evidence | Zero items missing; zero calls; a "nothing to backfill" message; success exit. |
| Every eligible item already embedded (re-run) | Missing set is empty; zero calls; no rows added/changed; success exit. |
| Per-item embedding failure (rate limit, network, malformed response) | That item returns `None` from `EmbeddingService._embed`, is logged by `type(exc).__name__` only, skipped; the rest of the batch continues. |
| Estimate exceeds budget threshold, interactive, no `--yes` | Planned-call count shown; proceeds only on confirmation; aborts without spending on decline. |
| Unknown / never-ingested repository (CLI) | Empty reader results → nothing to backfill; success exit with a "no analyses stored" message, matching existing CLI empty-result messaging. |
| Unknown repository (API) | 404 via the existing `_require_repository_exists` / `database_is_provisioned` gate, consistent with other per-repo endpoints. |

---

## Security considerations

- **No new credential.** Reuses the existing `OPENAI_API_KEY` (via `build_embedding_client()`)
  and never logs it.
- **No new untrusted-input boundary.** The backfill embeds only already-validated summary text;
  raw repository content (commit messages, diffs, discussion bodies) never reaches the embedding
  client through this path — the same guarantee spec 023 established, inherited by reusing
  `EmbeddingService`.
- **Failure logging leaks nothing.** Per-item failures are logged by exception *type name*
  only, never the raw exception or the text being embedded — matching `EmbeddingService._embed`.
- **Explicit, user-initiated spend.** Because the backfill is never auto-triggered and always
  passes through the budget guardrail, it cannot cause surprise cost on startup or on key
  presence.

---

## Privacy considerations

- No new category of data leaves the process. The same already-public, already-validated summary
  text that the live pipeline embeds is what the backfill embeds — no additional exposure beyond
  what spec 023 already accepted.

---

## Observability

- On no-key: a `_logger.debug`/info line and a user-facing "needs OPENAI_API_KEY" message; no
  call made.
- Per-item failure: `_logger.warning("embedding failed: %s", type(exc).__name__)` — reused
  verbatim from `EmbeddingService`.
- On completion: a counts-only summary (embedded N, skipped M, already-present K) to stdout
  (CLI) and to the dashboard progress state — no summary text, no vectors logged.
- The dashboard control reuses the existing in-memory progress-state pattern
  (`_analyze_progress` + lock in `api/routes/repos.py`), exposing running/done/total/error, so
  the UI can poll a status endpoint exactly as it does for analysis.

---

## Tests required

### Unit tests (TDD, failing first)

- `tests/unit/test_embedding_backfill_service.py`:
  - missing-set computation: given readers returning a known mix and
    `get_all_embeddings` returning a subset, only the complement is embedded;
  - idempotency: a second run with all items present makes zero embedding calls;
  - source-id keying: commit analyses key on `commit_sha`, discussion evidence keys on
    `discussion_url` (guards against a regression to the bare `discussion_id`);
  - per-item failure isolation: one embedder failure yields one skipped item, the rest persist,
    failure logged by type name only, raw text never in the log;
  - no-key no-op: with a `None` embedding client the service embeds nothing and reports the
    no-op cleanly;
  - estimate: `estimate_backfill_calls` returns exactly the count of missing items.
- `tests/unit/test_backfill_embeddings_cli.py`: new `backfill-embeddings` subcommand — budget
  estimate printed, `--yes` bypasses the prompt, decline aborts without spending, no-key path
  prints the explanatory message and returns success, injected fakes for readers/embedder
  (mirrors `test_analyze_commits_cli.py`'s structure and its `budget_confirm_fn` injection).
- `tests/unit/test_repos_backfill_endpoint.py` (or extend the repos route tests): the new
  endpoint returns 404 for an unknown repository, starts the background backfill for a known one,
  and exposes progress/status; no-key path returns a clean "unavailable" result rather than an
  error.
- `tests/integration/test_embedding_backfill_roundtrip.py`: with a real
  `SqliteEmbeddingStore`, seed `commit_analyses`/`discussion_evidence` and a partial set of
  `embedding_vectors`, run the backfill against a fake embedder, and assert the resulting
  `embedding_vectors` table has exactly one row per eligible item, correct PKs, and a re-run
  adds nothing (true end-to-end idempotency at the storage layer).

### TDD order

Backfill service (missing-set + idempotency + isolation, with fakes) → estimate/count →
composition factory (no-key wiring) → CLI command → API endpoint + progress → dashboard control.
Same layering the module already uses.

---

## Evaluation required

No new LLM-output eval is needed — the backfill produces no new interpreted claim, only vectors
over already-validated summaries. The correctness properties that matter (idempotency, missing-set
math, per-item isolation, no-key no-op) are deterministic and fully covered by the unit and
integration tests above rather than by a probabilistic eval. If the existing semantic-search eval
(spec 023) asserts retrieval quality, a single added assertion that a backfilled corpus is
retrievable identically to a live-embedded one would be a reasonable, optional extension —
decided at build time.

---

## Documentation impact

- A future build batch creates `docs/progress/{area}/batch-{N}-embedding-backfill.md` (area:
  `ingestion` or `pipeline`) and adds the entry to `docs/progress/README.md` in the same commit.
- **`README.md` must be updated** once this ships: the two "old analyses are not backfilled
  automatically" statements (line 75 and line 149) become inaccurate — they should be revised to
  point at the new backfill command/button as the supported way to enable semantic search for a
  repository analyzed before the OpenAI key was configured.
- `docs/architecture.md` Roadmap and `docs/specs/index.md` get this spec's row (added by this
  change).

---

## ADR impact

**Assessment: no new ADR needed.** The backfill introduces no new architectural decision: it
reuses the spec 023 embedding store, service, ports, and the `build_embedding_client()`
availability gate verbatim; it reuses the batch-38 budget guardrail mechanics; and it reuses
`EmbeddingService`'s existing per-item failure isolation. It is a mechanical catch-up path over
already-decided patterns — the same reasoning spec 026 used to conclude "no new ADR." The one
genuinely new *product* decision (manual trigger vs. auto-on-key) is captured here as a locked
Goal/Non-goal with its rationale, which does not rise to an ADR because it changes no boundary,
dependency, or data model.

---

## Open questions

1. **Exact CLI command name.** Proposed `git-it backfill-embeddings <repo>` (consistent with the
   verb-noun `analyze-commits`, `list-analyses` convention in `interfaces/cli.py`). Not locked —
   `backfill-embeddings` vs. `embed-existing` vs. a `--backfill` flag on an existing command
   should be confirmed against how the command reads in help output.
2. **Dashboard control label and exact placement.** Proposed a per-repo button in
   `_buildRepoCard(repo)` (`src/git_it/static/app.js`), labeled e.g. "Enable semantic search" or
   "Backfill embeddings", shown only when the repo has items missing embeddings **and** a key is
   configured. Deciding the visibility signal requires a small status endpoint returning a
   "missing embeddings" count per repository (there is no such reader today — `get_all_embeddings`
   returns full chunks, and there is no `count_missing_embeddings`); whether to add a dedicated
   count endpoint or compute it inline is a build-time decision.
3. **Estimate helper location.** Whether `estimate_backfill_calls` lives on the new backfill
   service (proposed) or is folded into an existing estimator. It cannot reuse
   `CommitAnalysisService.estimate_llm_calls` directly — that counts *unanalyzed commits*, a
   different quantity than *analyzed items missing an embedding*.
4. **Budget threshold reuse vs. its own default.** Proposed: reuse the existing
   `_DEFAULT_BUDGET_THRESHOLD` (50) and confirmation callback from `interfaces/cli.py` rather
   than introducing a separate embedding threshold. Embedding calls are cheaper per call than
   analysis calls, so a distinct (higher) threshold could be argued — not locked.
5. **API surface shape.** Whether the endpoint is `POST
   /api/repos/{repository_id}/embeddings/backfill` with a companion status route (mirroring the
   analyze/estimate/status trio) or a single synchronous call. The analyze pattern
   (`_analyze_bg` + progress + status) is the proposed template.

---

## Out of scope

- Any implementation (backfill service, composition factory, CLI command, API endpoint,
  dashboard control, tests) — deferred to a future build batch.
- Embedding `ReleaseEvidence` / `AdvisoryEvidence` — no source-type literal exists; explicit
  non-goal, consistent with spec 026.
- Auto-triggering on key presence or startup — explicit non-goal.
- Re-embedding already-embedded items or model-migration re-vectorization.
- Any scheduler / background cron for the backfill.
