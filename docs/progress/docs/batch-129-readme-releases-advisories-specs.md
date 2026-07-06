## Batch 129 — Specs 025 (README/CHANGELOG context) and 026 (Releases + Security Advisories)

### Goal

User asked to check for any other GitHub-derived knowledge-base source for the LLM beyond
what's already ingested, and evaluate feasibility/cost/convenience. This is new-feature/
data-model/LLM-prompt/security territory, so per CODEX.md this triggered `grill-me-with-docs`
before any implementation — this batch is **spec-only**, no production code changes ship here.

### What was checked before proposing anything

Grepped `infrastructure/github.py` for existing fetchers to ground the recommendation in
actual code, not assumption: exactly three exist today — `GithubContextFetcher` (per-commit
PR/issue enrichment, ADR 007), `GithubRepoMetadataFetcher` (stars/languages, spec 019),
`GithubDiscussionsFetcher` (spec 022). Nothing for README/docs, releases, or security
advisories. Presented four candidate sources with a cost/value ranking (README/CHANGELOG —
free, already cloned locally; Releases/Security Advisories — cheap, one REST call each;
PR-review-comments/full Issue threads — same LLM-summarization cost class as Discussions but
lower signal; Wiki — separate clone, real engineering cost, not all repos have one).

### Questioning round (grill-me-with-docs)

Two rounds of `AskUserQuestion` (2 + 2 questions), all answered:

1. **Spec scope**: two separate specs, not one combined — README/docs (no new API call, no new
   credential) has a fundamentally different cost/security profile than Releases/Advisories
   (new REST calls). Matches how spec 019 and spec 022 were scoped independently despite both
   being GitHub-derived evidence.
2. **README/docs file scope**: root-level `README.md`/`CHANGELOG.md` only — no recursive
   `docs/` folder scan, which would risk unbounded prompt-budget growth and require its own
   truncation/summarization strategy this simpler option avoids entirely.
3. **README/docs treatment**: raw-truncate only (~2000 chars), no LLM summarization call, fed
   into the narrative prompt as background context — zero new LLM calls, no new `EvidenceRef`
   type, since this is framing/context rather than a discrete cited claim.
4. **Releases/Advisories token gating**: verified empirically (via authenticated *and*
   anonymous `curl`/`gh api` calls against `axios/axios`) that both endpoints work with zero
   authentication for public repos, at a 60 req/hour anonymous rate limit — then confirmed the
   spec should still skip entirely without `GITHUB_TOKEN`, matching every existing fetcher's
   convention, rather than exploiting the anonymous path and introducing an inconsistent
   posture.
5. **Releases/Advisories citation model**: citable evidence, summarized like
   `DiscussionEvidence` (not raw-truncated like README) — release notes and advisory
   descriptions carry discrete, specific claims (versions, CVE-like details), closer in kind to
   Discussions than to README's general purpose-framing.

### What was added

- `specs/025-readme-changelog-context.md` (new, Draft) — `ProjectDocContent` domain model,
  `GitPythonProjectDocReader` (reads blobs from the bare clone's `HEAD` tree via GitPython —
  confirmed via `infrastructure/git.py:144`'s `--bare` flag that no working tree exists, so a
  plain filesystem read isn't possible; mirrors `GitPythonDefaultBranchReader`'s exact
  approach, spec 020/batch 96), `SqliteProjectDocStore`/`PostgresProjectDocStore`, optional-port
  wiring into `RepositoryIngestionService` (mirrors default-branch capture exactly), a new
  `## Project Documentation` narrative section, 8 Gherkin ACs, and an explicit "no new ADR
  needed" assessment (mechanical reuse of already-decided patterns).
- `specs/026-releases-and-security-advisories.md` (new, Draft) — `Release`/`SecurityAdvisory`
  raw domain types, `ReleaseEvidence`/`AdvisoryEvidence` validated/persisted types (evidence_ref
  sourced from Git It's own trusted API response, never LLM output — same ADR 015 citation-trust
  mitigation Discussions already uses), `ReleaseSummarizer`/`AdvisorySummarizer` (one LLM call
  per item, same untrusted-text preamble and per-item failure isolation as
  `DiscussionSummarizer`), two new fetchers (skip entirely without `GITHUB_TOKEN`), draft-release
  and withdrawn-advisory exclusion, 7 Gherkin ACs, and an explicit non-goal: extending spec 023's
  RAG/embedding pipeline to these two new evidence types is deferred to a future spec, not
  folded in here.
- `docs/specs/index.md` — added rows for 025/026 (Draft).

### Tests added

None — this batch is spec-authoring only. Both specs' "Tests required" sections define the TDD
order a future build batch must follow.

### Gate

`uv run --group docs mkdocs build --strict` — exit 0, no new warnings (specs live at the repo
root, outside the mkdocs `docs/` tree; only the `docs/specs/index.md` edit is in scope).

### Gotchas

- Verified the GitHub Security Advisories and Releases endpoints' actual public-access behavior
  empirically (real `gh api`/anonymous `curl` calls against `axios/axios`, which has real
  published advisories) rather than trusting memory of GitHub's API docs — both work
  unauthenticated for public repos. This directly shaped the token-gating grill question; had I
  assumed instead of verified, I might have written the spec around a false "requires elevated
  permissions" premise.
- The two specs are architecturally asymmetric on purpose: spec 025 has zero new LLM calls
  (raw truncation), spec 026 has one LLM call per release/advisory (schema-validated
  summarization) — this wasn't an oversight, it followed directly from the user's own answer
  that release/advisory content carries more discrete, citation-worthy claims than a README's
  general project-purpose framing.
- Spec 026 explicitly does NOT extend spec 023's (already-shipped, closed) RAG embedding
  pipeline to the two new evidence types — flagged as a real, separate architectural decision
  rather than silently scope-creeping into previously-closed code.

### Commits

- `docs: add spec 025 (README/CHANGELOG context) and spec 026 (releases and security advisories)`
