## Batch 111 — Fetch and summarize discussions at ingest time (spec 022, slice 5)

### Goal

Wire spec 022's GitHub Discussions evidence pipeline into the live ingest flow.
This is the last of the spec-022 build slices: fetcher (batch 108), summarizer
(batch 109), and narrative integration (batch 110) already existed but were
never invoked outside tests. After this batch, a successful `POST
/api/repos/ingest` fetches qualifying discussions, summarizes them via LLM,
stores the evidence, and the narrative service reads it back when generating a
case study — end-to-end, live.

### Why

Spec 022 mandated evidence-grounded discussion claims in case studies, but
nothing triggered the pipeline during real ingestion. Without this slice the
foundation, fetcher, and summarizer were dead code reachable only from unit
tests.

### What was added

**`src/git_it/repository_ingestion/composition.py`**
- `build_discussion_summarizer(*, model: str) -> DiscussionSummarizer` — new
  factory, mirrors the other `build_*` factories; wraps `LiteLLMLLMClient`.
- `build_narrative_service(...)` — now passes
  `discussion_reader=build_discussion_evidence_store(project_root=project_root)`
  in **both** the PostgreSQL and SQLite branches. `build_discussion_evidence_store`
  is already backend-aware, so calling it in both branches is correct and keeps
  the two branches symmetric.

**`src/git_it/api/routes/repos.py`**
- New imports: `GithubDiscussionsFetcher` (from `infrastructure.github`),
  `build_discussion_summarizer` and `build_discussion_evidence_store` (from
  `composition`).
- New helper `_fetch_and_store_discussion_evidence(*, repository_id,
  canonical_url, project_root) -> None`, mirroring
  `_fetch_and_store_repo_metadata` (spec 019) exactly: best-effort, guarded by
  `GITHUB_TOKEN` presence, catches `Exception` broadly and logs only
  `type(e).__name__` (never the exception message, the token, or discussion
  content) via `_logger.warning`.
- `_ingest_bg`'s `COMPLETED` branch now calls
  `_fetch_and_store_discussion_evidence(...)` immediately after the existing
  `_fetch_and_store_repo_metadata(...)` call, with the same `repository_id` /
  `canonical_url` / `project_root` arguments.

### Tests added

`tests/unit/test_api_repos.py` (+7):
- `test_fetch_and_store_discussion_evidence_skips_without_token` — no
  `GITHUB_TOKEN` → `GithubDiscussionsFetcher` never constructed.
- `test_fetch_and_store_discussion_evidence_stores_when_present` — fetcher
  returns a discussion, a stubbed summarizer (no real LLM call) returns
  evidence → the evidence is persisted and readable via
  `build_discussion_evidence_store(...).get_discussion_evidence(...)`.
- `test_fetch_and_store_discussion_evidence_noop_when_no_discussions` — fetcher
  returns `[]` → `build_discussion_summarizer` is never called, nothing stored.
- `test_fetch_and_store_discussion_evidence_noop_when_summarizer_returns_empty`
  — summarizer drops the only discussion → nothing stored.
- `test_fetch_and_store_discussion_evidence_swallows_exceptions` — fetcher
  raises `RuntimeError` → helper returns `None` without raising (best-effort /
  never-fail-ingestion guarantee, spec 022).
- `test_build_discussion_summarizer_returns_discussion_summarizer` — factory
  returns a `DiscussionSummarizer` instance.
- `test_build_narrative_service_wires_discussion_reader` — the built
  `NarrativeService._discussion_reader` is not `None`, proving the reader is
  wired (composition wiring test — no existing `test_composition.py` file to
  extend, so added alongside the other composition-adjacent tests in this
  file).

Full suite: **873 passed, 21 skipped** (baseline before this batch: 866 passed,
21 skipped; +7 passing, no regressions). Ran the complete suite, not just the
new tests, since `build_narrative_service` is exercised by many existing
narrative/regen/analyze tests.

Gates: `ruff check .`, `ruff format --check .`, and `mypy src/` all pass clean.

### Gotchas

- Ruff's `F821` flags quoted forward-reference return-type annotations
  (`-> "Discussion"`) as undefined names in this codebase (no `from __future__
  import annotations` in the test file). Removed the return-type hints from
  the two new test factory helpers (`_make_discussion`,
  `_make_discussion_evidence`) rather than adding the future-import repo-wide.
- The helper never touches raw `Discussion.title`/`.body`/`.answer_body`
  directly — it only passes the list through to
  `DiscussionSummarizer.summarize(...)`, which is the sole consumer of that
  untrusted text (per batch 109's security note). Only the schema-validated
  `DiscussionEvidence` list reaches the store.

### Commits

- `feat: fetch and summarize discussions at ingest time (spec 022)`
