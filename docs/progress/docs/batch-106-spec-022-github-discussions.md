## Batch 106 — Spec 022: GitHub Discussions ingestion and narrative evidence

### Goal

Write the grill-me-with-docs spec for a new evidence source — GitHub Discussions — before any
implementation begins. This is a spec-only batch: the build (fetcher, summarizer, stores,
composition wiring, narrative integration, tests, evals) is explicitly deferred to a future
batch.

### What was added

**`docs/specs/022-github-discussions.md`** — a `Status: Draft` spec following the exact
`grill-me-with-docs` section structure, encoding these locked product/technical decisions as
resolved requirements (not open questions):

- **Qualify/skip filter**: a discussion is summarized only if `category == "Q&A"` with an
  accepted answer, OR engagement is above threshold — `upvoteCount + reactionCount >= 5`
  (`DISCUSSION_MIN_ENGAGEMENT_SCORE`) OR reply count `>= 3` (`DISCUSSION_MIN_REPLY_COUNT`).
  Both are configurable, environment-backed constants with these defaults.
- **Evidence role**: discussions are cited only for design/decision rationale and recurring
  pain points; every discussion-sourced narrative claim must carry a citation link to the
  specific discussion URL — held to the same evidence discipline as commits/PRs. No
  free-floating discussion summary without a URL.
- **Volume bound**: fetch and rank candidates, keep the top ~20 by engagement
  (`DISCUSSION_MAX_SUMMARIZED = 20`), LLM-summarize each into a 1-2 line schema-validated
  `DiscussionEvidence` record *before* narrative generation — bounding both LLM cost and
  prompt size.
- **Raw-text-never-rendered guarantee**: the raw `Discussion` dataclass (title/body/answer
  text) is never persisted or serialized — only the validated `DiscussionEvidence.summary` +
  `discussion_url` ever reach storage, the API, or the UI.
- **Technical shape**: inline GraphQL `POST` to `https://api.github.com/graphql` reusing
  `infrastructure/github.py`'s existing `urllib.request` transport (no new dependency);
  graceful degradation when `GITHUB_TOKEN` is absent (same posture as spec 019's
  stars/languages fetch); a new `discussions.py` sub-module in both
  `infrastructure/sqlite/` and `infrastructure/postgres/` packages, re-exported from each
  `__init__.py`, wired through a new `build_discussion_evidence_store()` factory in
  `composition.py`; cursor-based GraphQL pagination (`DISCUSSION_PAGE_SIZE = 50`,
  `DISCUSSION_MAX_PAGES = 10`) with a hard cap so a huge repository can't cause unbounded
  fetching.
- **Narrative integration point**: `NarrativeService` gains an optional
  `discussion_reader: DiscussionEvidenceReader | None` dependency; `_build_user_message`/
  `_build_incremental_user_message` append a `## Discussion Evidence` block inside the
  existing `[REPOSITORY DATA]` envelope, one line per item with an explicit `source:` URL.
- Twelve Gherkin acceptance criteria (qualify via accepted-answer, qualify via each engagement
  path, skip low-engagement, token-absent degradation, evidence-link enforcement, volume cap,
  raw-text-never-rendered, schema validation, pagination hard cap) — testable without the
  original conversation.
- Security section covering prompt injection from discussion bodies, the untrusted-input
  boundary, URL validation for citation links, and no-secret-leakage.
- ADR impact assessed as **likely warranted** (new external GraphQL surface + a second
  untrusted-text-as-LLM-input call site) but explicitly deferred as a follow-up, not written
  in this batch.
- Three genuinely open questions (GraphQL token-scope requirements, closed/archived-repo
  discussion inclusion, whether engagement thresholds should be tunable) — everything else is
  recorded as a locked, resolved decision.

### Tests added

None — spec-only batch; implementation and its tests are deferred to a future build batch.

### Gotchas

- **Fetch/summarize trigger point required a design call not explicit in the brief.** The
  brief's locked decisions describe *what* gets fetched/filtered/summarized but not *when*.
  Mirrored spec 019's precedent (`GithubRepoMetadataFetcher`, fetched once inside `_ingest_bg`
  after `IngestionResult.status == "COMPLETED"`) rather than fetching at every narrative
  generation call, since discussions change slowly and this keeps `RepositoryIngestionService`
  free of GitHub API knowledge, consistent with spec 019's existing rationale.
- **Incremental-narrative diffing was resolved as a non-goal**, not left open: since the
  discussion-evidence set is already bounded to ≤20 short summaries, every narrative
  generation (full or incremental) resends the complete stored set — no "new since last
  generation" diffing logic is needed for this evidence source, unlike commit analyses.
- **Out-of-tree links**: every reference to `AGENTS.md`, `CODEX.md`, `ADR/*.md`, and other
  spec files inside `docs/specs/022-github-discussions.md` is plain backtick text, not a Markdown
  link — `mkdocs.yml`'s `docs_dir: docs` means `mkdocs build --strict` cannot resolve links
  pointing outside the `docs/` tree (same convention documented in batch 83 and re-confirmed
  in batch 102).

### Commits

- `docs: add spec 022 for GitHub Discussions ingestion and narrative evidence`
