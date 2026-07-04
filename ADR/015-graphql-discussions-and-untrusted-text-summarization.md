# ADR 015: Use GraphQL for GitHub Discussions and Summarize Untrusted Text Before Use

Status: Accepted
Date: 2026-07-04
Decision makers: TBD

## Context

Spec 022 (GitHub Discussions ingestion and narrative evidence) introduced two
things this repository had not needed before, and its own "ADR impact" section
flagged both as crossing the threshold that warrants a dedicated ADR rather than
a spec-level note alone:

1. **A second external GitHub API surface.** `infrastructure/github.py` already
   calls the GitHub REST API (`GithubContextFetcher` for per-commit PR/issue
   enrichment, `GithubRepoMetadataFetcher` for stars/languages — ADR 007).
   GitHub's REST API does not expose Discussions in a usable form; only the
   GraphQL API does. This is the first place Git It talks to GitHub over
   GraphQL, and a decision about when GraphQL vs. REST is the right tool for a
   *future* GitHub-adjacent feature is architecturally relevant beyond this one
   feature.
2. **A second LLM call site whose sole input is untrusted, external,
   community-authored text.** The existing narrative-generation LLM call
   (`NarrativeService`) is already fed untrusted-derived content, but only
   *Git It's own* structured analyses of that content (commit summaries,
   pattern reports) — one level removed from the raw diffs/messages. The new
   `DiscussionSummarizer` (`application/discussion_summarizer.py`) is
   different: its prompt input is the *raw* `Discussion.title`/`body`/
   `answer_body` fields, verbatim, straight from a public GitHub Discussion —
   text no Git It code has filtered, truncated, or restructured first. ADR 008
   already establishes "treat repository content as untrusted" as a blanket
   posture; this ADR records the *specific* mitigations required when untrusted
   text is the direct, unmediated LLM input, rather than repeating the general
   posture.

Both slices shipped across batches 107-111; this ADR records the decisions
already implemented, closing the deferral spec 022 flagged.

## Decision

### 1. GraphQL is used only where REST is insufficient; REST remains the default

`GithubDiscussionsFetcher` (`infrastructure/github.py`) performs an inline
GraphQL `POST` to `https://api.github.com/graphql` — the only GraphQL call site
in the codebase. It reuses the same `urllib.request`-based transport, `Bearer`
token header, `10s` timeout, and `_parse_owner_repo` validation helper already
established for the REST-based `GithubContextFetcher` and
`GithubRepoMetadataFetcher` (ADR 007), so no new HTTP client dependency was
added.

The rule going forward: **GraphQL is the exception, chosen only when a specific
GitHub feature (like Discussions) has no adequate REST equivalent.** REST stays
the default surface for everything else — it is simpler to reason about, easier
to test with straightforward JSON fixtures, and matches the rest of this
module's existing conventions. A future feature must justify GraphQL the same
way this one did (a concrete REST gap), not adopt it as a general preference.

The GraphQL query string itself is a fixed, hardcoded template; only `owner`,
`repo`, and the pagination `after` cursor are parameterized, and all three come
from Git It's own canonical-URL parsing or a prior page's response — never from
discussion content — so there is no GraphQL-injection surface via discussion
text.

### 2. Untrusted text as direct LLM input requires its own explicit mitigations

`DiscussionSummarizer` sends one raw `Discussion`'s `title`/`body`/
`answer_body` per LLM call — this is the untrusted-input boundary, and
`Discussion` never crosses it a second time. The mitigations actually
implemented:

- **Per-discussion untrusted-data security preamble.** The summarization prompt
  carries an explicit instruction to treat the discussion text as raw data to
  describe, never as instructions to follow, and to disregard any embedded
  attempt to override behavior — the same posture already used in
  `narrative_service._BASE_PROMPT`, scoped here to a single discussion instead
  of a whole repository history.
- **The URL/id trust boundary.** `discussion_url` in the resulting
  `DiscussionEvidence` is never taken from the LLM's own output as free text;
  the only value that can validate is one matching
  `https://github.com/{owner}/{repo}/discussions/{number}`
  (`domain/discussions.py`'s `field_validator`), sourced from the trusted
  `Discussion.url`/GitHub API response used to build the summarization call —
  never invented or rewritten by the model. A prompt-injected response cannot
  turn a citation link into an arbitrary or off-site URL.
- **Schema validation of every `DiscussionEvidence`.** Every LLM response is
  validated against the Pydantic model before it is allowed to exist as a
  `DiscussionEvidence` instance at all: `confidence` bounded `[0.0, 1.0]`,
  `claim_type` restricted to `Literal["design_rationale", "pain_point"]`,
  `discussion_url` validated as above, required fields present. A response
  that fails validation is dropped — logged, isolated to that one discussion —
  and does not abort summarization of the rest of the batch.
- **Raw discussion text never persisted, logged, or rendered.** `Discussion`
  (`domain/discussions.py`) is a frozen dataclass with no writer anywhere in
  the codebase — no store, no log statement, no API response touches its
  `title`/`body`/`answer_body`. Only the validated `DiscussionEvidence.summary`
  and `discussion_url` cross into `SqliteDiscussionEvidenceStore`/
  `PostgresDiscussionEvidenceStore`, the narrative prompt's `## Discussion
  Evidence` block, and any API/UI surface. This is the same "facts vs.
  interpretations" discipline ADR 004 established for commit analyses, applied
  here to community-authored text instead of diffs.

## Consequences

### Positive

- A second, precedent-setting GraphQL call site exists without adding a GraphQL
  client dependency — it reuses the existing REST transport conventions,
  keeping the module's HTTP surface uniform.
- The mitigations for "untrusted text as direct LLM input" are now explicit and
  reusable guidance for any future feature that summarizes community text
  (issue comments, review threads, etc.), rather than being re-derived from
  first principles each time.
- The evidence-link and schema-validation discipline gives every
  discussion-sourced narrative claim the same traceability CODEX.md already
  requires for commit-derived claims.

### Negative

- Two GitHub API conventions (REST and GraphQL) now coexist in
  `infrastructure/github.py`, adding a small amount of surface area a
  contributor must understand (different request/response shape, different
  pagination model).
- The per-discussion LLM call adds up to 20 additional LLM calls per ingestion
  (bounded by `DISCUSSION_MAX_SUMMARIZED`), a real cost/latency addition beyond
  the existing per-commit and narrative-generation calls.
- A discussion whose evidence is dropped for schema-validation failure is
  silently absent from the narrative — acceptable per spec 022, but it means an
  operator cannot easily tell, without checking logs, that a discussion was
  seen but rejected.

### Neutral

- This does not change the trust posture for commits, diffs, or PR/issue text
  established by ADR 007/008 — it extends the same posture to a new content
  source (Discussions) and a new API surface (GraphQL).
- A future feature that also needs GraphQL (e.g. GitHub Projects) can point to
  this ADR's fetcher as a template, rather than requiring a new architectural
  decision each time GraphQL is the right tool.

## Alternatives considered

- **Use REST-only workarounds for Discussions** (e.g. scraping or an
  unsupported endpoint): rejected — no adequate REST equivalent exists for
  Discussions data (category, accepted answer, reactions, comments).
- **Adopt a third-party GraphQL client library**: rejected — the existing
  `urllib.request`-based transport already handles auth, timeout, and error
  mapping consistently; a GraphQL query is just a JSON POST body, so a new
  dependency would add weight without capability.
- **Feed raw discussion text directly into the main narrative-generation
  prompt** (skip the per-discussion summarization step): rejected — this would
  reintroduce the exact untrusted-direct-input risk this ADR mitigates, at a
  much larger prompt-injection surface (up to 20 raw bodies per narrative call
  instead of one bounded validated summary each), and blow the prompt budget
  (spec 022's Problem section).
- **Trust LLM-returned URLs for citations**: rejected — a prompt-injected
  summarization response could otherwise fabricate or redirect a citation link;
  sourcing the URL from Git It's own trusted `Discussion.url` closes that path.

## Security impact

- No new secret-handling surface: `GITHUB_TOKEN` reuse follows the same
  never-logged convention already in place for REST calls in this module.
- The untrusted-input boundary for discussion text is exactly one
  summarization call per discussion; `Discussion` is never passed to any other
  function that stores, logs, or renders it.
- Citation URLs are independently validated against a fixed pattern and sourced
  from trusted data, not LLM output — closing the "LLM invents an off-site
  link" risk class.
- GraphQL query parameterization is limited to Git-It-controlled values
  (owner, repo, cursor), never discussion content, closing the
  GraphQL-injection risk class.

## Quality impact

- TDD coverage across batches 107-111: fetcher qualify/rank/pagination/failure
  behavior (`test_github_discussions_fetcher.py`), summarizer schema
  enforcement and per-item failure isolation (`test_discussion_summarizer.py`),
  store roundtrip/upsert (`test_discussion_evidence_store_sqlite.py`,
  extended `test_postgres_adapters.py`), and narrative integration
  (`test_narrative_service.py`).
- Batch 112 adds `evals/discussion_evidence_eval.py`, the first automated,
  API-key-gated eval asserting no raw discussion text leaks into a generated
  narrative — the deterministic security property this ADR's mitigations are
  meant to guarantee.

## Documentation impact

- `specs/022-github-discussions.md` — the spec this ADR closes the deferred
  ADR-impact item for.
- `docs/adr/index.md` — this ADR's row.
- `evals/README.md` — documents the new discussion-evidence eval.

## Links

- `specs/022-github-discussions.md`
- ADR 007 (Use Local Git Mining Plus GitHub MCP) — REST API boundary this ADR's
  GraphQL decision extends.
- ADR 008 (Treat Repository Content as Untrusted) — the general posture this
  ADR specializes for direct untrusted-text LLM input.
- ADR 004 (Separate Facts from Interpretations) — the facts-vs-interpretations
  discipline `Discussion` vs. `DiscussionEvidence` mirrors.
