# Feature Spec: GitHub Releases and Security Advisories as Cited Narrative Evidence

**Status:** Draft
**Spec number:** 026
**Author:** Rafael Castaño
**Date:** 2026-07-06

---

## Summary

Add two new evidence sources to the case-study narrative, both fetched via GitHub's REST API
(gated on `GITHUB_TOKEN` presence, matching every existing GitHub fetcher's convention) and
each turned into schema-validated, citeable evidence through its own summarization step —
architecturally identical to spec 022's `Discussion` → `DiscussionSummarizer` →
`DiscussionEvidence` pipeline, applied to **Releases** (`GET
/repos/{owner}/{repo}/releases`) and **Security Advisories** (`GET
/repos/{owner}/{repo}/security-advisories`). Both endpoints were empirically confirmed to work
with zero authentication for public repos (anonymous rate limit: 60 requests/hour) — this spec
deliberately does not rely on that, choosing instead to skip entirely without a token, for
consistency with `GithubContextFetcher`/`GithubRepoMetadataFetcher`/`GithubDiscussionsFetcher`,
which all already follow that exact "hidden without token" posture.

---

## Problem

Git It's narrative can currently cite commit-derived facts (spec 001+), pattern reports (spec
003), and Discussion-derived design rationale/pain points (spec 022) — but has no visibility
into a project's own release history or its disclosed security vulnerabilities. Both are
high-signal, already-public, already-curated sources: a release's notes are the maintainers'
own account of what changed and why; a security advisory is a specific, dated, severity-rated
claim about a real vulnerability and its fix. Neither today informs "what mistakes were made"
or "how did this project evolve" questions the Ask tab and case study are meant to answer.

---

## Goals

1. New `ReleaseEvidence` and `AdvisoryEvidence` domain types (mirrors `DiscussionEvidence`
   exactly in shape and validation discipline), each independently summarized from raw
   GitHub API data via a dedicated LLM call, schema-validated before being allowed to exist.
2. Both fetchers (`GithubReleasesFetcher`, `GithubSecurityAdvisoriesFetcher`) skip entirely —
   no API call at all — when `GITHUB_TOKEN` is absent, matching every existing GitHub fetcher
   in `infrastructure/github.py`. (Locked decision, confirmed with the user: this is a
   deliberate consistency choice, not a technical requirement — both endpoints were verified
   to work anonymously for public repos, at a much lower 60 req/hour rate limit shared across
   every other feature in this process; hiding without a token avoids that shared quota risk
   and keeps one uniform "needs GITHUB_TOKEN" story across the whole file.)
3. Each `ReleaseEvidence`/`AdvisoryEvidence` carries an `evidence_ref` (a validated GitHub URL,
   sourced from Git It's own trusted API response — never from the LLM's own output) so a
   narrative claim built from either stays evidence-linked exactly like `DiscussionEvidence`
   already is (CODEX.md evidence-before-interpretation; mirrors ADR 015's citation-trust
   mitigation).
4. Draft releases and withdrawn security advisories are excluded at the fetch layer — never
   summarized, never surfaced. Only published, non-draft releases and non-withdrawn advisories
   are eligible evidence.
5. Per-item failure isolation identical to `DiscussionSummarizer`'s posture: one release or
   advisory failing to summarize (LLM error, malformed response, schema-validation failure)
   never aborts the rest of the batch.

---

## Non-goals

- Embedding `ReleaseEvidence`/`AdvisoryEvidence` into the RAG semantic-search index (spec 023).
  Spec 023 is fully shipped and closed; extending its embedding pipeline to two new source
  types is a real, separate architectural decision (new `EmbeddedChunk.source_type` literals,
  new `EmbeddingService` methods, `SemanticSearchService`/`search_similar_commits` surfacing a
  third/fourth source type) deliberately deferred to a future spec rather than folded in here.
- Dependabot alerts (a different, permission-gated API requiring push access even for public
  repos — not the same endpoint or trust model as published Security Advisories).
- GitHub Projects/milestones, roadmap data, or any planning-oriented API.
- Anonymous (no-`GITHUB_TOKEN`) operation, despite being technically possible — explicitly
  rejected in this round for consistency (see Goals #2).
- Diffing/tracking advisory or release edits over time. Only the current state at fetch time
  is ever summarized; re-ingestion re-fetches and re-summarizes (upsert), same posture as
  Discussions.
- A UI surface for browsing releases/advisories directly (no new REST endpoint, no new
  frontend view) — this feeds the narrative prompt only, same scope boundary spec 022 used.

---

## Users

- **Learner**: reading a case study, benefits from concrete "here's what shipped and when" and
  "here's a real vulnerability that was found and fixed" evidence, grounded in the project's
  own disclosed history rather than inferred from commit messages alone.
- **Operator**: this feature is entirely optional and additive — absent `GITHUB_TOKEN`,
  ingestion/analysis/narrative generation work exactly as they do today.

---

## User stories

1. **As a learner**, I want the case study to be able to cite a specific release ("as of
   v2.0.0...") or a specific disclosed vulnerability ("a SQL injection was fixed in
   GHSA-xxxx...") with a working link back to GitHub.
2. **As an operator**, when `GITHUB_TOKEN` is not set, I want this feature to be silently
   absent — no error, no degraded behavior elsewhere.
3. **As an operator**, when one release or advisory fails to summarize (rate limit, malformed
   response), I want that single item skipped, not the whole ingestion aborted.
4. **As a learner**, I want draft releases and withdrawn advisories to never appear as cited
   evidence, since neither represents a real, disclosed, current fact about the project.

---

## Acceptance criteria

```gherkin
Feature: GitHub Releases and Security Advisories as cited narrative evidence

  Scenario: Release fetched and summarized when GITHUB_TOKEN is set
    Given GITHUB_TOKEN is set and a repository has at least one published, non-draft release
    When the repository is ingested
    Then the release is fetched, summarized, and persisted as ReleaseEvidence
    And its evidence_ref is a valid github.com/.../releases/tag/{tag} URL

  Scenario: Security advisory fetched and summarized when GITHUB_TOKEN is set
    Given GITHUB_TOKEN is set and a repository has at least one published, non-withdrawn
      security advisory
    When the repository is ingested
    Then the advisory is fetched, summarized, and persisted as AdvisoryEvidence
    And its evidence_ref is a valid github.com/.../security/advisories/{ghsa_id} URL

  Scenario: GITHUB_TOKEN absent — both features entirely hidden
    Given GITHUB_TOKEN is not set
    When a repository is ingested
    Then no Releases or Security Advisories API call is made
    And no ReleaseEvidence or AdvisoryEvidence is persisted
    And ingestion completes exactly as it does today

  Scenario: Draft releases and withdrawn advisories are excluded
    Given a repository has a draft release and a withdrawn security advisory, alongside
      published/non-withdrawn ones
    When the repository is ingested
    Then only the published release and the non-withdrawn advisory are summarized
    And the draft release and withdrawn advisory are never fetched-for-summarization

  Scenario: Per-item summarization failure does not abort the batch
    Given the summarization call fails for one release (timeout, malformed response) among
      several
    When ingestion continues
    Then that one release has no persisted ReleaseEvidence
    And every other release/advisory is summarized and persisted normally
    And the failure is logged with only its exception type name

  Scenario: Narrative cites release/advisory evidence when present
    Given a repository has persisted ReleaseEvidence and/or AdvisoryEvidence
    When a case study narrative is generated
    Then the prompt includes this evidence with its evidence_ref
    And the SYSTEM_PROMPT-equivalent narrative instructions require citing it by evidence_ref
      when used

  Scenario: A prompt-injected release/advisory description cannot fabricate its own citation
    Given a release or advisory whose raw text attempts to instruct the summarization model to
      output a different URL or claim type
    When it is summarized
    Then the persisted evidence_ref still validates against the URL pattern sourced from Git
      It's own trusted API response, never from the model's free-text output
    And a response failing schema validation (bad claim_type, out-of-range confidence,
      malformed evidence_ref) is dropped, not persisted
```

---

## Domain concepts

- **`Release`** (new frozen dataclass, `domain/releases.py`; raw, ephemeral, never
  persisted — mirrors `Discussion`): `tag_name: str`, `name: str | None`, `body: str | None`
  (raw release-notes markdown), `html_url: str`, `published_at: str | None`, `prerelease:
  bool`. Draft releases are filtered out by the fetcher and never construct a `Release` at all.
- **`SecurityAdvisory`** (new frozen dataclass, `domain/advisories.py`; raw, ephemeral): `ghsa_id:
  str`, `cve_id: str | None`, `summary: str`, `description: str`, `severity: str`, `html_url:
  str`, `published_at: str | None`. Withdrawn advisories are filtered out by the fetcher.
- **`ReleaseEvidence`** (new frozen dataclass, `domain/releases.py`; validated, persisted):
  `tag_name: str`, `release_url: str` (the `evidence_ref`, validated by `field_validator`
  against `https://github.com/{owner}/{repo}/releases/tag/{tag}`, sourced from `Release.html_url`
  — never LLM-generated), `claim_type: Literal[...]` (exact taxonomy an open question, proposed
  below), `summary: str`, `confidence: float` (`[0.0, 1.0]`), `limitations: list[str]`,
  `source_inputs: list[str]`, `generated_at: datetime`, `model: str`.
- **`AdvisoryEvidence`** (new frozen dataclass, `domain/advisories.py`; validated, persisted):
  `ghsa_id: str`, `advisory_url: str` (`evidence_ref`, validated against
  `https://github.com/{owner}/{repo}/security/advisories/{ghsa_id}`, sourced from
  `SecurityAdvisory.html_url`), `severity: str` (validated against GitHub's known severity
  values: `low`/`medium`/`high`/`critical`), `summary: str`, `confidence: float`,
  `limitations: list[str]`, `source_inputs: list[str]`, `generated_at: datetime`, `model: str`.
- **`ReleaseSummarizer`** / **`AdvisorySummarizer`** (new application services,
  `application/release_summarizer.py` / `application/advisory_summarizer.py` — mirror
  `DiscussionSummarizer` exactly): one LLM call per item, carrying the same untrusted-data
  security preamble already established for `DiscussionSummarizer` (ADR 015 §2) — the raw
  `body`/`description` text is the untrusted-input boundary, never crossed a second time.
  Per-item failure isolation: schema-validation or LLM-call failure drops that one item,
  logged by exception type name only, never aborts the batch.
- **`GithubReleasesFetcher`** / **`GithubSecurityAdvisoriesFetcher`** (new classes,
  `infrastructure/github.py`, alongside the three existing fetchers): reuse the exact same
  `urllib.request` transport, `Bearer` token header, 10s timeout, and `_parse_owner_repo`
  helper. `if self._token is None: _logger.debug(...); return []` — identical short-circuit to
  every existing fetcher. Bounded by `RELEASE_MAX_SUMMARIZED` / `ADVISORY_MAX_SUMMARIZED`
  (env-var-backed constants, batch-74 convention; exact defaults an open question below) to
  cap per-ingestion LLM-call cost, mirroring `DISCUSSION_MAX_SUMMARIZED` (spec 022).
- **`SqliteReleaseEvidenceStore`/`PostgresReleaseEvidenceStore`** and
  **`SqliteAdvisoryEvidenceStore`/`PostgresAdvisoryEvidenceStore`** (new stores, one upserted
  row per `(repository_id, tag_name)` / `(repository_id, ghsa_id)` — mirror
  `discussion_evidence`'s store shape exactly).
- **Trigger point (locked, mirrors spec 022's discussion-fetch wiring exactly)**: a new
  `_fetch_and_store_release_evidence` / `_fetch_and_store_advisory_evidence` helper in
  `api/routes/repos.py`, called from `_ingest_bg` alongside the existing
  `_fetch_and_store_discussion_evidence`/`_fetch_and_store_repo_metadata` calls — best-effort,
  never blocks or fails the ingestion run.
- **`NarrativeService`** gains optional `release_evidence_reader` /
  `advisory_evidence_reader` constructor parameters (mirrors `discussion_reader`), appending
  a `## Release History` / `## Security Advisories` section to the prompt when non-empty, each
  entry showing its `evidence_ref` for citation.

---

## Inputs and outputs

- `Release(tag_name, name, body, html_url, published_at, prerelease)` (`domain/releases.py`)
- `SecurityAdvisory(ghsa_id, cve_id, summary, description, severity, html_url, published_at)`
  (`domain/advisories.py`)
- `ReleaseEvidence(tag_name, release_url, claim_type, summary, confidence, limitations,
  source_inputs, generated_at, model)` (`domain/releases.py`)
- `AdvisoryEvidence(ghsa_id, advisory_url, severity, summary, confidence, limitations,
  source_inputs, generated_at, model)` (`domain/advisories.py`)
- `GithubReleasesFetcher(token).fetch_releases(canonical_url: str) -> list[Release]`
  (`infrastructure/github.py`)
- `GithubSecurityAdvisoriesFetcher(token).fetch_advisories(canonical_url: str) ->
  list[SecurityAdvisory]` (`infrastructure/github.py`)
- `ReleaseSummarizer(llm_client).summarize(release: Release) -> ReleaseEvidence | None`
  (`application/release_summarizer.py`)
- `AdvisorySummarizer(llm_client).summarize(advisory: SecurityAdvisory) -> AdvisoryEvidence |
  None` (`application/advisory_summarizer.py`)
- Stores: `.initialize()` / `.save_release_evidence(repository_id, items)` (upsert) /
  `.get_release_evidence(repository_id) -> list[ReleaseEvidence]`, and the advisory
  equivalents.

---

## Evidence requirements

- Every `ReleaseEvidence`/`AdvisoryEvidence` carries its `evidence_ref` (`release_url` /
  `advisory_url`), sourced exclusively from Git It's own trusted API response
  (`Release.html_url` / `SecurityAdvisory.html_url`) and independently re-validated by a
  `field_validator` against a fixed URL pattern — never trusted as free-text LLM output.
  Identical citation-trust mitigation to `DiscussionEvidence.discussion_url` (ADR 015).
- The narrative's evidence-citation instruction (already present for Discussions) must be
  extended to name release/advisory evidence explicitly, so a claim built from either is cited
  by its `evidence_ref`.

---

## Failure modes

| Failure | Expected behavior |
|---|---|
| `GITHUB_TOKEN` unset | Both fetchers return `[]` immediately; no API call; nothing persisted; ingestion/narrative otherwise unaffected. |
| Releases/Advisories REST call fails (HTTP error, network error, timeout, rate limit) | That fetch returns `[]` for this ingestion; logged at WARNING with `type(exc).__name__` only; ingestion continues normally. |
| Per-item summarization failure (LLM error, malformed response) | That one item is dropped (`None`), logged by exception type name only; the rest of the batch continues. |
| Schema validation failure (bad `claim_type`/`severity`, out-of-range `confidence`, malformed `evidence_ref`) | The item is dropped, never persisted — same posture as `DiscussionEvidence`. |
| Draft release / withdrawn advisory present | Filtered out before ever reaching the summarizer — never fetched-for-summarization, never persisted. |
| Repository re-ingested | Re-fetches and re-summarizes; upserts on `(repository_id, tag_name)` / `(repository_id, ghsa_id)` — a release/advisory published since the last ingestion is picked up; one already summarized is re-summarized (accepted cost, same as Discussions). |

---

## Security considerations

- **A second, discrete use of the untrusted-direct-LLM-input mitigations ADR 015
  established** — `body`/`description` text is raw, external, community/maintainer-authored
  content, fed directly to a summarization call exactly like `Discussion.title/body/answer_body`
  already is. The same mitigations apply verbatim: untrusted-data security preamble in the
  summarization prompt, schema validation of every response, evidence-URL sourced from trusted
  API data (never LLM output), raw text never persisted/logged/rendered beyond the one
  summarization call.
- **No new credential** — reuses the existing `GITHUB_TOKEN`, same never-logged convention.
- **Anonymous access exists but is deliberately not used** (see Goals #2) — this is a
  risk-avoidance choice (shared 60 req/hour anonymous quota), not a security requirement; worth
  stating plainly since a future contributor might otherwise "helpfully" remove the token gate
  having seen it work anonymously in manual testing.
- **`severity` is validated against GitHub's known enum**, not trusted as arbitrary LLM output,
  closing a path where a prompt-injected advisory description could otherwise inflate/deflate
  the reported severity in a way that misleads a learner.

---

## Privacy considerations

- Release notes and published security advisories are already-public GitHub content (same
  assumption already accepted for Discussions/commits) — no new category of *repository* data
  exposure, though this is a second/third piece of already-public content now flowing through
  an LLM summarization call, worth the same disclosure treatment spec 022 already gives
  Discussions.

---

## Observability

Every summarization call emits a structured log record via the spec 024 mechanism
(`call_site="release_summarization"` / `call_site="advisory_summarization"`), metadata only —
no raw release/advisory text, no summary text in the log. Mirrors spec 022/023's interim
posture where spec 024 isn't yet wired to a given call site: `_logger.debug` on skip (no
token), `_logger.warning` on failure (`type(exc).__name__` only), `_logger.info`/`debug` after
a batch completes with counts only.

---

## Tests required

### Unit tests (TDD, failing first)

- `tests/unit/test_releases_domain.py` / `test_advisories_domain.py`: `Release`/
  `SecurityAdvisory`/`ReleaseEvidence`/`AdvisoryEvidence` construction, field validation
  (`evidence_ref` pattern, `severity` enum, `confidence` bounds).
- `tests/unit/test_github_releases_fetcher.py` / `test_github_security_advisories_fetcher.py`:
  no-token skip, non-GitHub-URL skip, happy path, draft/withdrawn filtering, HTTP
  error/malformed JSON handling, `RELEASE_MAX_SUMMARIZED`/`ADVISORY_MAX_SUMMARIZED` bound
  respected — mirrors `test_github_discussions_fetcher.py`'s structure.
- `tests/unit/test_release_summarizer.py` / `test_advisory_summarizer.py`: schema enforcement,
  per-item failure isolation, untrusted-text security preamble present in the prompt, raw text
  never appears in logs on failure (secret/content-leak guard, mirrors
  `test_embedding_service.py`'s equivalent tests).
- `tests/unit/test_release_evidence_store_sqlite.py` / `test_advisory_evidence_store_sqlite.py`:
  roundtrip, upsert, unknown repository, cross-repository independence, `initialize()`
  idempotency.
- `tests/unit/test_postgres_adapters.py` (extended): both new stores' roundtrip + upsert,
  gated by the existing `DATABASE_URL` skip marker.
- `tests/unit/test_narrative_service.py` (extended): prompt includes release/advisory
  evidence with its `evidence_ref` when present; absent entirely when neither exists.
- A schema-level test asserting the summarization call site never receives text containing a
  sentinel value planted only in a raw `Release.body`/`SecurityAdvisory.description` fixture —
  the deterministic unit-testable form of "no raw text leakage," mirroring spec 022/023's
  equivalent tests.

### TDD order

Domain (`Release`/`SecurityAdvisory`/`*Evidence`) → fetchers → summarizers → stores (SQLite →
Postgres) → ingest wiring → narrative integration — same layering convention specs 022/023
already used.

---

## Evaluation required

Extend `evals/discussion_evidence_eval.py`'s pattern (or add a new
`evals/release_advisory_eval.py`, decided at build time) asserting the same three properties
spec 022's eval already checks for Discussions, applied to Release/Advisory evidence: citation
completeness, no raw-text leakage, and — since severity is now a structured field — a
deterministic check that a high/critical-severity advisory's evidence is never presented with
hedged/uncertain language the way a genuinely low-confidence claim might be (severity and
confidence are independent axes; this guards against conflating "the advisory's severity is
low" with "our confidence in this summary is low").

---

## Documentation impact

- A future build batch creates `docs/progress/{area}/batch-{N}-releases-advisories.md`.
- `docs/progress/README.md` gets a new entry.
- `docs/prompt-contracts/narrative-generation.md` gets the two new evidence sections
  documented, mirroring how spec 022 updated the same file for Discussion Evidence.

---

## ADR impact

**Assessment: no new ADR needed.** Both fetchers reuse the exact REST transport/auth
convention ADR 007 already established (no new API surface — unlike spec 022's GraphQL
addition). Both summarizers reuse ADR 015's untrusted-direct-LLM-input mitigations verbatim,
applied to two more content types rather than specializing the posture further. This spec is a
mechanical extension of two already-decided patterns, not a new architectural decision —
matching spec 020's own "no new ADR" conclusion for the same reason.

---

## Open questions

1. **`ReleaseEvidence.claim_type` taxonomy.** Proposed: `Literal["breaking_change",
   "feature_release", "bugfix_release", "security_release"]` — not locked; should be
   confirmed/tuned during implementation against how release notes actually read in practice.
2. **`RELEASE_MAX_SUMMARIZED` / `ADVISORY_MAX_SUMMARIZED` exact values.** Proposed: latest 10
   releases, latest 10 advisories (by published date) — not locked, mirrors
   `DISCUSSION_MAX_SUMMARIZED`'s existence but not necessarily its exact number.
3. **Prerelease inclusion.** Proposed: include non-draft prereleases (only exclude drafts) —
   not locked; could instead exclude prereleases too if they prove to be narrative noise.
4. **Advisory severity enum exact values.** Proposed: GitHub's own
   `low`/`medium`/`high`/`critical` — should be confirmed against the live API response shape
   during implementation, not assumed from memory.

---

## Out of scope

- Implementation of any kind (domain models, fetchers, summarizers, stores, narrative wiring,
  tests, eval) — deferred to a future build batch.
- Embedding either evidence type into the RAG/semantic-search index (spec 023) — explicit
  non-goal, future spec if wanted.
- Dependabot alerts, GitHub Projects/milestones.
- Anonymous (no-token) operation.
- Spec 025 (README/CHANGELOG context) — a separate, independent spec per the confirmed scope
  split; already drafted.
