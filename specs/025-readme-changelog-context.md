# Feature Spec: README/CHANGELOG Context for Case Study Narratives

**Status:** Draft
**Spec number:** 025
**Author:** Rafael Castaño
**Date:** 2026-07-06

---

## Summary

Capture each repository's root-level `README`/`CHANGELOG` file (if present) once at ingestion
time, from the same bare git clone already used for commit mining — no new API call, no new
credential — and inject a truncated excerpt into the case-study narrative prompt as a new
"## Project Documentation" context block. This grounds the narrative's opening and overall
framing in the maintainers' own stated purpose for the project, instead of relying solely on
inference from commit diffs and messages.

---

## Problem

`NarrativeService` currently builds the case-study prompt from commit analyses, pattern
reports, and (since spec 022) discussion evidence — but never from the project's own
documentation. Spec 015 (batch 88) already requires the narrative's opening to be
repo-specific and non-generic, but the LLM has to *infer* what the project is from commit
content alone. A project's README almost always states its purpose more directly and
reliably than any commit message does, and costs nothing extra to obtain — the full repo is
already cloned locally for every ingestion (`infrastructure/git.py`'s `--bare` clone).

---

## Goals

1. Capture `README.md`/`README.rst` and `CHANGELOG.md`/`CHANGELOG.rst` (root-level only, no
   `docs/` folder, no nested paths) from the bare clone's `HEAD` tree, once per ingestion —
   mirroring the "compute once, persist" discipline already used for commit facts and
   default-branch capture (spec 020, batch 96).
2. No new external API call, no new credential. This works identically whether or not
   `GITHUB_TOKEN` is set, since it reads only from the local git clone already required for
   commit mining — unlike every other GitHub-derived evidence source in this codebase (specs
   019/022), which are gated on `GITHUB_TOKEN`.
3. Content is truncated (not summarized) to a fixed character budget and injected into the
   narrative prompt as background/context — not as a discrete, per-claim cited fact. No new
   `EvidenceRef`-style citation type. (Locked decision, confirmed with the user: raw-truncate
   over LLM-summarization, since this is scene-setting context, not a claim needing individual
   evidence-linking the way `DiscussionEvidence`/`CommitAnalysis` are.)
4. Graceful, total degradation when neither file exists: no context block is added, nothing
   fails, no error surfaced — matches the "optional evidence source" posture already
   established for discussions/repo metadata/default branch.

---

## Non-goals

- `docs/` folder, `CONTRIBUTING.md`, wiki, or any nested/non-root file. Explicitly rejected in
  this round (locked decision) — root `README`/`CHANGELOG` only. A future spec can extend
  scope if it proves valuable; this one does not attempt to bound a much larger, variable-size
  input.
- LLM summarization of the captured text (contrast with spec 022's `DiscussionSummarizer`).
  Raw truncation only.
- A new evidence/citation type surfaced to the Ask tab's `search_similar_commits` (spec 023) or
  any other RAG-adjacent mechanism. This spec only touches case-study narrative generation.
- Re-fetching on every re-analysis. Same "fetch once, keep" posture as spec 020's default
  branch capture — a README/CHANGELOG that changes after first ingestion is not refreshed
  until the repository's next ingestion pass rebuilds the clone (out of scope here; same
  accepted staleness spec 020 already documents for default branch).
- Diffing/summarizing *changes* to CHANGELOG.md over time. Only the current `HEAD` version is
  ever captured.

---

## Users

- **Learner**: reading a case study, benefits from an opening/framing that reflects the
  project's own stated purpose, not just an LLM's best guess from commit content.
- **Operator**: ingestion behaves identically with or without `GITHUB_TOKEN` — this context
  source never depends on it.

---

## User stories

1. **As a learner**, when a repository has a README, I want the case study's framing to
   reflect what the README says the project actually is, not just an inference from commits.
2. **As an operator**, when a repository has neither a README nor a CHANGELOG, I want ingestion
   and narrative generation to proceed exactly as before, with no error and no missing
   functionality.
3. **As an operator**, I want this to add zero new external API calls or credentials — it must
   work identically for a repository ingested with or without `GITHUB_TOKEN` set.

---

## Acceptance criteria

```gherkin
Feature: README/CHANGELOG context for case study narratives

  Scenario: README captured and persisted at ingestion time
    Given a repository whose HEAD tree contains a README.md
    When the repository is ingested successfully
    Then the README's text (truncated to the configured character budget) is persisted,
      keyed to that repository_id

  Scenario: CHANGELOG captured independently of README
    Given a repository whose HEAD tree contains a CHANGELOG.md but no README
    When the repository is ingested successfully
    Then the CHANGELOG's text is persisted
    And no README entry is created

  Scenario: Neither file present — no error, nothing persisted
    Given a repository whose HEAD tree contains neither a README nor a CHANGELOG (in any
      supported casing/extension)
    When the repository is ingested successfully
    Then no project-doc record is persisted
    And ingestion completes with its normal COMPLETED status

  Scenario: Narrative prompt includes the captured context when present
    Given a repository with a persisted README and/or CHANGELOG excerpt
    When a case study narrative is generated
    Then the prompt includes a "## Project Documentation" block containing the truncated text

  Scenario: Narrative prompt omits the block entirely when absent
    Given a repository with no persisted README or CHANGELOG
    When a case study narrative is generated
    Then the prompt contains no "## Project Documentation" block

  Scenario: Oversized file is truncated, not rejected
    Given a README larger than the configured character budget
    When it is captured at ingestion time
    Then only the first N characters are persisted
    And the truncation does not raise an error

  Scenario: Binary or undecodable blob content does not abort ingestion
    Given a file matching the README/CHANGELOG name pattern whose blob content cannot be
      decoded as UTF-8 text
    When ingestion captures project-doc content
    Then that one file is skipped (logged by exception type name only)
    And ingestion of the rest of the repository is unaffected

  Scenario: Case sensitivity and common extensions
    Given a repository using "Readme.md", "README.rst", or "readme.markdown" instead of
      exactly "README.md"
    When ingestion captures project-doc content
    Then a reasonable case-insensitive match against the supported name/extension list still
      captures it
```

---

## Domain concepts

- **`ProjectDocContent`** (new frozen dataclass, `domain/project_docs.py`): `repository_id:
  str`, `readme_text: str | None`, `readme_truncated: bool`, `changelog_text: str | None`,
  `changelog_truncated: bool`, `captured_at: datetime`. One record per repository (not one row
  per source) — simpler than a generic key-value shape, since there are always exactly two
  possible sources.
- **`ProjectDocReader`** (new `Protocol`, `application/ports.py`): `.get_project_docs(
  repository_id: str) -> ProjectDocContent | None`.
- **`ProjectDocWriter`** (new `Protocol`, `application/ports.py`): `.save_project_docs(content:
  ProjectDocContent) -> None` (upsert).
- **`GitPythonProjectDocReader`** (new class, `infrastructure/commits.py` or a new
  `infrastructure/project_docs.py` — decided at build time): opens the bare clone at
  `repository_cache_path(project_root, repository_id=...)` via GitPython (mirrors
  `GitPythonDefaultBranchReader`'s exact approach, spec 020), reads `HEAD`'s tree, looks up
  blobs matching a case-insensitive name/extension list (`readme.md`, `readme.rst`,
  `readme.markdown`, `readme.txt`, `readme` with no extension; same pattern for `changelog`),
  decodes as UTF-8 (`errors="replace"` or skip on failure — locked at implementation time),
  truncates to `PROJECT_DOC_MAX_CHARS` (env-var-backed constant, default proposed: 2000,
  following the batch-74 convention). Returns `None` for a file that doesn't exist; never
  raises for a missing/binary/oversized file.
- **`SqliteProjectDocStore` / `PostgresProjectDocStore`** (new stores, one upserted row per
  `repository_id` in a new `project_docs` table: `repository_id PK, readme_text TEXT NULL,
  readme_truncated INTEGER/BOOLEAN, changelog_text TEXT NULL, changelog_truncated
  INTEGER/BOOLEAN, captured_at`). Independent table from `default_branch_metadata` and
  `repo_metadata` — same rationale spec 020 already used (different capture trigger, no
  token-gating, avoid loosening an unrelated already-shipped contract).
- **Capture trigger (locked, mirrors spec 020's default-branch capture exactly)**: inside
  `RepositoryIngestionService`, via new optional constructor ports (`project_doc_reader`,
  `project_doc_writer`), called right after a successful `clone_or_fetch`, guarded the same
  way `default_branch_reader`/`writer` already are. Never called on gateway failure.
- **`build_project_doc_store()`** (new factory, `composition.py`): backend-aware, mirrors
  `build_default_branch_store`. No `build_project_doc_reader_client()`-style
  availability-gate factory is needed (unlike `build_embedding_client()`) — this feature has no
  credential to be absent; it is *always* available once ingestion succeeds.
- **`NarrativeService`** gains an optional `project_doc_reader: ProjectDocReader | None`
  constructor parameter (mirrors `discussion_reader`, spec 022). When present and non-empty,
  `_build_user_message` (or equivalent) appends a `## Project Documentation` section
  containing the truncated README text (if any) and/or CHANGELOG text (if any), each clearly
  labeled, wrapped in the same untrusted-data framing the prompt already applies to commit
  messages/diffs (ADR 008) — no new sanitization mechanism, since this is the same class of
  repository-derived text already covered by that blanket posture.

---

## Inputs and outputs

- `ProjectDocContent(repository_id, readme_text, readme_truncated, changelog_text,
  changelog_truncated, captured_at)` (`domain/project_docs.py`, frozen dataclass)
- `ProjectDocReader.get_project_docs(repository_id: str) -> ProjectDocContent | None`
  (`application/ports.py`, `Protocol`)
- `ProjectDocWriter.save_project_docs(content: ProjectDocContent) -> None` (`application/ports.py`,
  `Protocol`)
- `GitPythonProjectDocReader(cache_path: Path)` — reader implementation, read-only against the
  bare clone
- `SqliteProjectDocStore(database_path)` / `PostgresProjectDocStore(conninfo)` —
  `.initialize()` / `.save_project_docs(content)` (upsert) / `.get_project_docs(repository_id)
  -> ProjectDocContent | None`
- `build_project_doc_store(*, project_root) -> SqliteProjectDocStore | PostgresProjectDocStore`
  (`composition.py`)
- `RepositoryIngestionService.__init__` gains optional `project_doc_reader`,
  `project_doc_writer` keyword params (mirrors `default_branch_reader`/`writer`)
- `NarrativeService.__init__` gains optional `project_doc_reader: ProjectDocReader | None`
  keyword param

---

## Evidence requirements

This context is **not** a discrete, cited claim — it is background/framing context, the same
role `repo_context`-style inputs already play in the narrative prompt. No new `EvidenceRef`
citation format is introduced. The narrative must not present a specific README/CHANGELOG
sentence as if it were an independently-verified fact distinct from what the maintainers
themselves wrote — the prompt should frame this block explicitly as "the project's own stated
description," preserving CODEX.md's facts-vs-interpretations discipline (ADR 004) by being
honest about the *source* of this framing, not by fabricating a citation mechanism for it.

---

## Failure modes

| Failure | Expected behavior |
|---|---|
| Neither README nor CHANGELOG present | No `ProjectDocContent` persisted; narrative prompt has no new section; no error. |
| File present but not decodable as UTF-8 | That one file is treated as absent (logged by exception type name only); the other file (if present) is still captured normally. |
| File larger than `PROJECT_DOC_MAX_CHARS` | Truncated to the budget; `readme_truncated`/`changelog_truncated` flag set `True`; never raises. |
| Bare-clone read failure (corrupted clone, GitPython error) | Captured as `None` for that ingestion, logged by exception type name only; ingestion's overall COMPLETED status is unaffected — mirrors `GitPythonDefaultBranchReader`'s "never raises" contract exactly. |
| Repository re-ingested (re-fetch, not re-clone) | Same accepted staleness as spec 020's default branch: content captured at the *first* ingestion is not refreshed on subsequent `git fetch`-only re-ingestions in this spec's scope. |

---

## Security considerations

- **Same untrusted-content boundary as every other repository-derived text (ADR 008)** —
  README/CHANGELOG text is repository content, authored by the project's own (untrusted, from
  Git It's perspective) maintainers/contributors, exactly like commit messages and diffs
  already are. No new trust boundary is introduced; this spec extends the *existing* boundary
  to one more content source.
- **Deliberately weaker mitigation than ADR 015's Discussion-summarization posture, by locked
  choice.** ADR 015 requires per-discussion LLM summarization *specifically because* raw
  Discussion text was judged to need schema-validated mediation before use. This spec instead
  feeds raw (truncated) text directly into the narrative prompt, relying solely on the
  existing "treat everything as untrusted data, never as instructions" prompt-level posture
  (`narrative_service._BASE_PROMPT`) — the same posture already covers raw commit
  messages/diffs today. This is an explicit, accepted risk-acceptance for this content
  specifically (background/framing text, not a discrete cited claim), not an oversight — call
  this out plainly in review rather than silently matching Discussions' stricter posture.
- **No new secret-handling surface.** No new credential is introduced (this spec has no
  external API call at all), so there is nothing new to leak.
- **Truncation, not the character budget itself, is the DoS/cost mitigation** — a maliciously
  huge README (e.g. a repository designed to bloat prompt size/cost) is bounded by
  `PROJECT_DOC_MAX_CHARS` regardless of the file's actual size on disk.

---

## Privacy considerations

- README/CHANGELOG content is already-public repository content (same assumption already
  accepted for commit messages and Discussions) — no new category of data exposure beyond
  what ingesting the repository already implies.

---

## Observability

Mirrors spec 024's posture: a capture attempt logs at `_logger.debug` on skip (neither file
found) and `_logger.warning` on a decode/read failure (`type(exc).__name__` only, never file
content). No new `observe_llm_call` call site is needed — this feature makes no LLM call at
all (locked "truncate only" decision).

---

## Tests required

### Unit tests (TDD, failing first)

- `tests/unit/test_project_docs_domain.py`: `ProjectDocContent` construction/shape.
- `tests/unit/test_git_project_doc_reader.py`: reads `README.md` from a real bare-clone
  fixture; reads `CHANGELOG.md` independently; case-insensitive name matching
  (`Readme.md`, `readme.rst`); missing file → `None`; oversized file → truncated with the
  `*_truncated` flag set; non-UTF8 blob → skipped, not raised; corrupted/missing clone path →
  `None` without raising (mirrors `test_default_branch_reader.py`'s structure).
- `tests/unit/test_project_doc_store_sqlite.py`: insert + read roundtrip; upsert overwrites;
  unknown repository → `None`; distinct repositories independent; `initialize()` idempotent.
- `tests/unit/test_postgres_adapters.py` (extended): `PostgresProjectDocStore` roundtrip +
  upsert, gated by the existing `DATABASE_URL` skip marker.
- `tests/unit/test_repository_ingestion_service.py` (extended): reader/writer called after a
  successful clone; writer not called when the reader returns `None` for both files; behavior
  unchanged when neither port is wired; reader/writer never called on a `GitGatewayError`
  (mirrors the existing default-branch wiring tests, spec 020).
- `tests/unit/test_narrative_service.py` (extended): prompt includes `## Project
  Documentation` with the correct truncated text when a `ProjectDocContent` is present;
  section is entirely absent when the reader returns `None`; README-only and CHANGELOG-only
  cases both render correctly; the section explicitly frames the text as the project's own
  documentation (not an independently-verified fact).

### TDD order

Domain (`ProjectDocContent`) → `GitPythonProjectDocReader` → stores (SQLite → Postgres) →
`RepositoryIngestionService` wiring → `NarrativeService` prompt integration — same layering
convention specs 020/022/023 already used.

---

## Evaluation required

Extend the existing repo-specific-opening eval (spec 015, batch 88) with one additional
fixture case: a repository whose README states a purpose in specific, distinctive language,
asserting the generated opening reflects that language rather than generic filler — this is a
prompt change per CODEX.md's quality baseline ("prompt changes still require an eval"), so a
targeted extension of the existing eval satisfies that requirement without needing a wholly
new eval script.

---

## Documentation impact

- A future build batch creates `docs/progress/{area}/batch-{N}-readme-changelog-context.md`.
- `docs/progress/README.md` gets a new entry.
- `docs/prompt-contracts/narrative-generation.md` gets the new `## Project Documentation`
  section documented, mirroring how spec 022 documented its discussion-evidence prompt
  section.

---

## ADR impact

**Assessment: no new ADR needed.** This spec does not introduce a new external dependency, new
credential, new API surface, or new architectural capability — it reuses the exact bare-clone
GitPython-read pattern ADR-adjacent work already established for spec 020's default-branch
capture, and extends ADR 008's existing untrusted-content posture to one more content source
rather than specializing it the way ADR 015 did for Discussions. If implementation reveals a
need to diverge from the "truncate only" decision (e.g. summarization is added later), that
would be the trigger for revisiting this assessment.

---

## Open questions

1. **Exact `PROJECT_DOC_MAX_CHARS` value.** Proposed default: 2000 characters, as a
   configurable env-var-backed constant (batch-74 convention) — not locked; should be tuned
   during implementation/evaluation against real README sizes and prompt-budget impact.
2. **Where `GitPythonProjectDocReader` lives** — alongside `GitPythonDefaultBranchReader` in
   `infrastructure/commits.py`, or a new dedicated `infrastructure/project_docs.py` module.
   Decided at build time based on file size/cohesion at that point.
3. **Decode-failure handling detail** — `errors="replace"` (best-effort mojibake-tolerant
   decode) vs. skip-the-file-entirely on any decode error. Proposed: skip entirely, matching
   this spec's "never raise, never produce garbled output" posture — but not locked.
4. **Re-fetch staleness** — if this proves valuable enough that operators want fresher
   README/CHANGELOG content without a full re-ingestion, that would need its own follow-up
   spec; explicitly out of scope here.

---

## Out of scope

- Implementation of any kind (domain model, stores, services, prompt wiring, tests, eval
  extension) — deferred to a future build batch.
- `docs/` folder, wiki, `CONTRIBUTING.md`, or any nested/non-root file.
- LLM summarization of captured content.
- Any change to the RAG/`search_similar_commits` tool (spec 023) or embeddings pipeline.
- Spec 026 (Releases + Security Advisories) — a separate, independent spec per the confirmed
  scope split.
