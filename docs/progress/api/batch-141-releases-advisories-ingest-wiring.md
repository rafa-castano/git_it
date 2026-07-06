## Batch 141 — Wire release and advisory evidence into ingestion (spec 026, slice 5)

### Goal

Wire spec 026's Release/Advisory evidence pipeline into the live ingest flow,
mirroring how batch 111 wired spec 022's Discussion evidence pipeline. Domain
models (batch 137), fetchers (batch 138), summarizers (batch 139), and stores
(batch 140) already existed but were never invoked outside tests. After this
batch, a successful `POST /api/repos/ingest` fetches published/non-draft
releases and published/non-withdrawn security advisories, summarizes each via
LLM, and persists the resulting evidence — end-to-end, live.

### Why

Spec 026 mandated evidence-grounded release/advisory claims in case studies,
but nothing triggered either pipeline during real ingestion. Without this
slice the fetchers, summarizers, and stores were dead code reachable only from
unit tests.

### What was added

**`src/git_it/repository_ingestion/composition.py`**
- `build_release_evidence_store(*, project_root) -> SqliteReleaseEvidenceStore | PostgresReleaseEvidenceStore`
  and `build_advisory_evidence_store(*, project_root) -> SqliteAdvisoryEvidenceStore | PostgresAdvisoryEvidenceStore`
  — new factories, mirror `build_discussion_evidence_store` exactly (backend-aware,
  initialize on the SQLite branch).
- `build_release_summarizer(*, model) -> ReleaseSummarizer` and
  `build_advisory_summarizer(*, model) -> AdvisorySummarizer` — new factories,
  mirror `build_discussion_summarizer`, wrapping `LiteLLMLLMClient` with
  `call_site="release_summarization"` / `call_site="advisory_summarization"`
  respectively.
- New imports: `PostgresReleaseEvidenceStore`, `PostgresAdvisoryEvidenceStore`,
  `SqliteReleaseEvidenceStore`, `SqliteAdvisoryEvidenceStore` (stores),
  `ReleaseSummarizer`, `AdvisorySummarizer` (application services).

**`src/git_it/api/routes/repos.py`**
- New imports: `GithubReleasesFetcher`, `GithubSecurityAdvisoriesFetcher` (from
  `infrastructure.github`); `build_release_evidence_store`,
  `build_release_summarizer`, `build_advisory_evidence_store`,
  `build_advisory_summarizer` (from `composition`).
- New helper `_fetch_and_store_release_evidence(*, repository_id,
  canonical_url, project_root) -> None`, mirroring
  `_fetch_and_store_discussion_evidence` exactly: best-effort, guarded by
  `GITHUB_TOKEN` presence, catches `Exception` broadly and logs only
  `type(e).__name__` via `_logger.warning`. **No embedding step** — spec 026
  explicitly excludes releases/advisories from the RAG embedding pipeline
  (spec 023 non-goal).
- New helper `_fetch_and_store_advisory_evidence(...)` — the symmetric
  version using `GithubSecurityAdvisoriesFetcher` / `fetch_advisories` /
  `build_advisory_summarizer` / `save_advisory_evidence`. Also no embedding
  step.
- `_ingest_bg`'s `COMPLETED` branch now calls both new helpers immediately
  after the existing `_fetch_and_store_discussion_evidence(...)` call, with
  the same `repository_id` / `canonical_url` / `project_root` arguments.

### Tests added

`tests/unit/test_api_repos.py` (+14):
- `test_fetch_and_store_release_evidence_skips_without_token` — no
  `GITHUB_TOKEN` → `GithubReleasesFetcher` never constructed.
- `test_fetch_and_store_release_evidence_stores_when_present` — fetcher
  returns a release, a stubbed summarizer (no real LLM call) returns evidence
  → the evidence is persisted and readable via
  `build_release_evidence_store(...).get_release_evidence(...)`.
- `test_fetch_and_store_release_evidence_noop_when_no_releases` — fetcher
  returns `[]` → `build_release_summarizer` never called, nothing stored.
- `test_fetch_and_store_release_evidence_noop_when_summarizer_returns_empty`
  — summarizer drops the only release → nothing stored.
- `test_fetch_and_store_release_evidence_swallows_exceptions` — fetcher
  raises `RuntimeError` → helper returns `None` without raising.
- The five symmetric tests for `_fetch_and_store_advisory_evidence`.
- `test_build_release_evidence_store_returns_sqlite_store` /
  `test_build_advisory_evidence_store_returns_sqlite_store` — factories
  return an initialized SQLite store under the default backend.
- `test_build_release_summarizer_returns_release_summarizer` /
  `test_build_advisory_summarizer_returns_advisory_summarizer` — factories
  return the right summarizer type.

Full suite: **1087 passed, 33 skipped** (baseline before this batch: 1073
passed, 33 skipped; +14 passing, no regressions). Ran the complete suite, not
just the new tests, since this touches the shared ingest path.

Gates: `ruff check .`, `ruff format --check .`, and `mypy src/` all pass
clean.

### Gotchas

- Neither new helper computes or persists embeddings — spec 026 explicitly
  lists extending the spec 023 RAG embedding pipeline to release/advisory
  evidence as a deferred non-goal, so `_fetch_and_store_discussion_evidence`'s
  embedding block was deliberately **not** replicated here.
- Both helpers only pass the raw `Release`/`SecurityAdvisory` list through to
  their respective summarizer's `.summarize(...)` call — the sole consumer of
  the untrusted `body`/`description` text (ADR 015). Only the
  schema-validated `ReleaseEvidence`/`AdvisoryEvidence` list reaches the
  store.

### Commits

- `feat: wire release and advisory evidence into ingestion (spec 026)`
