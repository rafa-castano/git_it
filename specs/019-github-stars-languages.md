# Spec 019: GitHub Stars + Language Breakdown

Status: Accepted
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: Architecture Agent, Security Agent, Quality Agent
Created: 2026-07-03
Updated: 2026-07-03

## 1. Summary

Git It already enriches commit analysis with GitHub PR/issue context
(`GithubContextFetcher`, spec-less batch 58) via `infrastructure/github.py`, gated
on a `GITHUB_TOKEN` environment variable and best-effort by design (absent token or
any fetch failure degrades silently, never blocks ingestion). This spec adds two
new, independent pieces of repository-level GitHub metadata — the star count
(`stargazers_count`) and the language byte-breakdown (`GET .../languages`) — fetched
once per repository during ingestion, persisted in a new store, exposed on
`GET /api/repos`, and rendered on each repository's home-screen card as a star
count and a GitHub-style horizontal stacked language bar with a legend.

## 2. Problem

A learner browsing the repository list has no signal today for a repository's
popularity (stars) or its technology composition (language mix) without leaving
Git It and opening GitHub directly. This is exactly the kind of at-a-glance
context that helps someone decide which case study to explore next.

## 3. Goals

- Fetch `stargazers_count` and the `language → bytes` map from the GitHub REST
  API once per repository, at ingestion time, reusing the same token, timeout,
  and error-handling conventions as the existing `github.py` adapter.
- Persist the fetched metadata (or its absence) in a new store with SQLite and
  PostgreSQL implementations, wired through the existing `_get_db_backend()` /
  `build_*` composition pattern.
- Expose `stars: int | None` and `languages: list[{language, bytes, percent}]`
  on `RepoSummary` (`GET /api/repos`).
- Render a ⭐ star count and a GitHub-style horizontal stacked language bar
  (with a legend of language + percent, shown via the existing tooltip system)
  on each repo card. Degrade to "nothing rendered" when data is absent — no
  layout break, no placeholder, no error text.

## 4. Non-goals

- Fetching stars/languages synchronously on every `GET /api/repos` call — this
  is a fetch-once-at-ingestion-time, read-from-store feature.
- Backfilling metadata for repositories ingested before this batch (see
  Domain concepts — the backfill gap is accepted and documented, not solved
  here).
- A generic "GitHub repo facts" extensibility mechanism — only stars and
  languages are in scope.
- Refreshing stars/languages on a schedule (e.g. nightly re-fetch) — out of
  scope; a repository's stars/languages are captured once, at ingestion time.
- Any change to the commit-level `GithubContextFetcher`/`GithubContext`
  (PR/issue enrichment) — this is a new, independent adapter class in the same
  module, not a modification of the existing one.

## 5. Users

- Learner: browsing the repository list on the home screen, wants a quick
  popularity/technology signal before choosing which repository's case study
  to open.

## 6. User stories

```md
As a learner browsing the list of ingested repositories,
I want to see each repository's star count and language composition,
so that I can gauge its popularity and technology stack before diving in,
without leaving Git It.
```

## 7. Acceptance criteria

### AC-01 — Metadata fetched once at ingestion time

```gherkin
Given a repository is ingested successfully (IngestionResult.status == "COMPLETED")
And GITHUB_TOKEN is set
And the canonical_url is a GitHub URL
When ingestion's background task completes
Then GithubRepoMetadataFetcher.fetch_repo_metadata(canonical_url) is called once
And, if it returns a RepoMetadata, it is persisted via the repo-metadata store
  keyed by repository_id
```

### AC-02 — Token absent → no fetch, no error

```gherkin
Given GITHUB_TOKEN is not set
When ingestion completes
Then no HTTP call is made for repo metadata
And the repository has no stored metadata (stars=None, languages=[] on read)
```

### AC-03 — Non-GitHub canonical URL → no fetch

```gherkin
Given the canonical_url does not match the github.com owner/repo pattern
When ingestion completes
Then no HTTP call is made for repo metadata
```

### AC-04 — HTTP error or malformed JSON on the stars call → no metadata stored

```gherkin
Given the GET /repos/{owner}/{repo} call raises an HTTPError, a network error,
  or returns a body that is not valid JSON or not a JSON object
When fetch_repo_metadata runs
Then it returns None
And nothing is written to the repo-metadata store for this ingestion
```

### AC-05 — Stars fetched but languages call fails → partial metadata with empty languages

```gherkin
Given the stars call succeeds with a valid integer stargazers_count
And the languages call raises an HTTPError, a network error, or returns
  malformed/non-dict JSON
When fetch_repo_metadata runs
Then it returns RepoMetadata(stars=<int>, languages=())
And the store persists stars with an empty languages list
```

This asymmetry (stars failure voids the whole result, languages failure only
empties one field) is a locked decision: stars is the headline field this
feature exists to show, so a failed stars fetch means "we have nothing
trustworthy to show"; languages is additive polish that degrades to "no bar
rendered" without invalidating the star count.

### AC-06 — Malformed language payload entries are dropped, not trusted

```gherkin
Given the languages payload contains a non-string key, a negative byte count,
  a non-numeric byte count, or is not a JSON object at all
When the payload is parsed
Then the offending entries are silently excluded from the result
And well-formed entries are still included
```

### AC-07 — API exposes stars and a percent-computed language breakdown

```gherkin
Given a repository has stored metadata with languages {"Python": 300, "HTML": 100}
When GET /api/repos is called
Then the matching RepoSummary has stars=<int>
And languages == [
      {"language": "Python", "bytes": 300, "percent": 75.0},
      {"language": "HTML",   "bytes": 100, "percent": 25.0}
    ]
  (order preserved from the stored/fetched order; percent = bytes / total_bytes * 100,
  rounded to 1 decimal place)
```

### AC-08 — Repository with no stored metadata degrades cleanly

```gherkin
Given a repository has no row in the repo-metadata store (pre-existing repo,
  ingested before this batch, or token was absent at ingestion time)
When GET /api/repos is called
Then the matching RepoSummary has stars=None and languages=[]
```

### AC-09 — Frontend renders stars + language bar only when present

```gherkin
Given a repo card is built for a RepoSummary with stars=None and languages=[]
When _buildRepoCard renders
Then no star badge and no language bar are rendered — no layout break, no
  placeholder text
Given a repo card is built for a RepoSummary with stars=1234 and a non-empty
  languages list
When _buildRepoCard renders
Then a "⭐ 1,234" badge is rendered
And a horizontal stacked bar is rendered with one segment per language
  (colored, width proportional to percent, languages beyond the 8th folded
  into a trailing "Other" segment), plus a legend list below showing each
  language name and percent, using the existing data-tip tooltip mechanism
  (not a native title attribute)
```

## 8. Domain concepts

- **`RepoMetadata`** (new frozen dataclass,
  `domain/repo_metadata.py`): `stars: int`, `languages: tuple[LanguageBreakdown, ...]`.
- **`LanguageBreakdown`** (new frozen dataclass, same module):
  `language: str`, `bytes: int`.
- **`GithubRepoMetadataFetcher`** (new class, `infrastructure/github.py`,
  alongside — not a modification of — `GithubContextFetcher`): fetches
  `GET /repos/{owner}/{repo}` (for `stargazers_count`) and
  `GET /repos/{owner}/{repo}/languages`, using the same `urllib.request`-based
  transport, `Bearer` token header, `10s` timeout, and `owner/repo` URL parsing
  helper (`_parse_owner_repo`) already used by `GithubContextFetcher`. Has no
  cache — it is called at most once per ingestion, not once per commit, so a
  persistent cache table would add complexity without a corresponding read
  pattern to justify it (unlike the per-commit `GithubContextCache`, which
  exists to make re-analysis idempotent and cheap).
- **`SqliteRepoMetadataStore` / `PostgresRepoMetadataStore`** (new stores,
  `infrastructure/sqlite.py` / `infrastructure/postgres.py`): one row per
  repository, upserted. `languages` stored as a JSON array of
  `{"language": ..., "bytes": ...}` objects, preserving GitHub's byte-descending
  response order.
- **`build_repo_metadata_store()`** (new factory, `composition.py`): mirrors
  `build_case_study_store()` — backend-aware, calls `.initialize()` for SQLite.
- **When metadata is fetched (locked decision)**: during ingestion, immediately
  after `RepositoryIngestionService.ingest()` returns `status == "COMPLETED"`,
  inside the existing `_ingest_bg()` background thread in
  `api/routes/repos.py` (the same place the route already runs the git
  clone/fetch + commit/file extraction pipeline). This is a deliberate
  placement choice, not inside `RepositoryIngestionService` itself: that
  service is a pure git-mining pipeline with no GitHub API knowledge today
  (only `commit_analysis_service`, via composition, currently talks to
  `api.github.com`, and only per-commit). Adding a GitHub HTTP call to
  `RepositoryIngestionService` would give a domain-adjacent application
  service a new external dependency it doesn't otherwise have. Orchestrating
  the fetch at the same route-level background-thread boundary that already
  owns "things that happen once, after a successful ingest" keeps the change
  small and consistent with how `_ingest_bg`/`_analyze_bg` are already
  structured in this file (background orchestration lives in the route layer;
  domain/application services stay narrowly scoped).
- **Backfill gap (accepted, documented)**: a repository ingested before this
  batch ships has no row in the new store. `GET /api/repos` returns
  `stars=None, languages=[]` for it — indistinguishable, from the API's point
  of view, from "token was absent at ingestion time." No backfill job is
  provided in this batch (non-goal). A future batch could add a
  `POST /api/repos/{id}/refresh-metadata` endpoint if this gap proves painful
  in practice.
- **Percent computation**: a pure mapper function,
  `map_languages(languages: tuple[LanguageBreakdown, ...]) -> list[LanguageItem]`
  in `api/mappers.py`. `percent = round(bytes / total_bytes * 100, 1)`; returns
  `[]` when `languages` is empty (avoids a division by zero).
- **Language bar palette (locked decision)**: the bar uses a new, dedicated
  8-slot categorical palette (defined as CSS custom properties,
  `--lang-1`..`--lang-8`, per light/dark theme) rather than reusing the app's
  existing `--blue/--green/--yellow/--orange/--red/--purple` variables. Two
  reasons: (1) those six variables already carry fixed status semantics
  elsewhere in the app (green = completed, red = delete/error, yellow =
  in-progress) that would be misleading if reused for arbitrary language
  identity (e.g. a "Rust" segment rendered in the same red used for delete
  buttons); (2) validating the existing six against the dataviz-skill
  categorical-palette checks (lightness band, CVD-safe adjacency, contrast)
  fails outright (lightness band FAIL on 3 of 6 hues) — they were designed as
  UI accent colors, not as a validated chart palette. The new 8-slot palette
  passes all checks in both themes (validated via
  `scripts/validate_palette.js` against this app's actual `--surface` values,
  `#1a1d27` dark / `#ffffff` light) with only a CVD-adjacency floor-band WARN,
  which is mitigated by the required legend (language name + percent) per the
  skill's relief rule. Repositories with more than 8 languages fold the
  remainder into a trailing "Other" segment in the muted/gray ink color (never
  a 9th generated hue).

## 9. Inputs and outputs

New/changed public interfaces:

- `RepoMetadata(stars: int, languages: tuple[LanguageBreakdown, ...] = ())`
- `LanguageBreakdown(language: str, bytes: int)`
- `GithubRepoMetadataFetcher(token: str | None).fetch_repo_metadata(canonical_url: str) -> RepoMetadata | None`
- `SqliteRepoMetadataStore(database_path).initialize()/.save_repo_metadata(repository_id, metadata)/.get_repo_metadata(repository_id) -> RepoMetadata | None`
- `PostgresRepoMetadataStore(conninfo)` — same contract
- `build_repo_metadata_store(*, project_root) -> SqliteRepoMetadataStore | PostgresRepoMetadataStore`
- `map_languages(languages) -> list[LanguageItem]` (`api/mappers.py`)
- `RepoSummary.stars: int | None = None`, `RepoSummary.languages: list[LanguageItem] = []`
  (`api/schemas.py`)
- Frontend: `_buildRepoCard` renders a stars badge and a language bar +
  legend when present; `app.css` gets `--lang-1`..`--lang-8` custom properties
  and `.rc-lang-bar`/`.rc-lang-seg`/`.rc-lang-legend` rules.

## 10. Evidence requirements

Not applicable in the CODEX.md sense (no LLM-generated interpretive claim is
involved) — stars and languages are raw, structurally-validated GitHub API
fields displayed as-is, not an inferred or narrated claim about repository
history.

## 11. Failure modes

| Failure | Behavior |
|---|---|
| `GITHUB_TOKEN` unset | No HTTP call; repo has no stored metadata; API/UI treat it as absent (AC-02, AC-08). |
| Canonical URL is not `github.com` | No HTTP call (AC-03). |
| Stars call: HTTP error, network error, timeout, malformed JSON, non-dict/non-int payload | `fetch_repo_metadata` returns `None`; nothing persisted (AC-04). |
| Languages call: HTTP error, network error, timeout, malformed JSON, non-dict payload | `languages=()` only; stars still persisted (AC-05). |
| Individual language entry: non-string key, non-numeric or negative byte count | That entry dropped; well-formed entries kept (AC-06). |
| Ingestion itself fails (non-`COMPLETED` status) | Metadata fetch is never attempted. |
| Pre-existing repository with no metadata row | API returns `stars=None, languages=[]`; UI renders nothing extra (AC-08, AC-09). |
| More than 8 distinct languages | First 8 by byte count shown individually; remainder summed into a trailing "Other" segment (never a 9th hue). |

## 12. Security considerations

- The GitHub API JSON response is untrusted input (ADR 008 / CODEX.md). Only
  two fields are read and validated: `stargazers_count` (must be a real `int`,
  not `bool`, else treated as fetch failure) from the repo endpoint, and the
  `language -> bytes` map from the languages endpoint (each key must be `str`,
  each value must coerce to a non-negative `int`, else that entry is dropped).
  No other field of either response is read, logged, or persisted.
- The `GITHUB_TOKEN` is never logged, matching the existing `github.py`
  convention (only `type(exc).__name__` is logged on failures, never response
  bodies or headers).
- No new attack surface on write paths: this feature is read-mostly from
  GitHub's perspective (two `GET` calls) and adds no new user-supplied input
  beyond the existing ingestion URL, which is already validated by
  `parse_repository_url`.
- Degrade-on-failure is itself a security-relevant property here: this
  adapter must never turn a partial/hostile GitHub response into an ingestion
  failure or an exception that propagates out of the background thread — it
  is wrapped the same way `_ingest_bg`/`_analyze_bg` already wrap their
  bodies (broad `except Exception`, logged by exception type only).

## 13. Privacy considerations

Stars and language-byte counts are already-public repository-level metadata
(the same data GitHub itself displays on the repository's public page). No
new personal data is collected, logged, or transmitted.

## 14. Observability

- `_logger.warning` on stars/languages fetch failure, logging only
  `type(exc).__name__` (never the exception body, matching the rest of
  `github.py`).
- `_logger.debug` on skip paths (no token, non-GitHub URL) — same level as
  the existing `GithubContextFetcher` skip logging.

## 15. Tests required

### Automated tests (pytest, TDD — failing first)

- `tests/unit/test_github_repo_metadata_fetcher.py` (new): happy path (stars +
  languages both succeed), no-token skip (no HTTP call made), non-GitHub URL
  skip, stars HTTP-error → `None`, stars malformed-JSON → `None`, stars
  non-dict-JSON → `None`, languages HTTP-error → `RepoMetadata(stars=N,
  languages=())`, malformed language entries dropped while valid ones kept,
  empty languages payload → `languages=()`.

  Mocking approach: `unittest.mock.patch("urllib.request.urlopen")`, the same
  mechanism already used by `tests/unit/test_github_api_fetcher.py` for
  `GithubContextFetcher`. **Deviation from the original brief**: the brief
  asked for `respx`-mocked HTTP; investigated and confirmed `github.py` uses
  stdlib `urllib.request`, not `httpx`, and `respx`/`httpx` are not
  dependencies anywhere in `pyproject.toml`. `respx` mocks `httpx` transports
  specifically — it cannot intercept `urllib`. Introducing `httpx` (and
  `respx`) into this one adapter would fork the codebase's GitHub-HTTP
  transport across two libraries for no functional gain and would add a new
  runtime dependency (`httpx`) purely to satisfy a testing preference,
  contradicting CODEX.md's "avoid unrelated refactors" / "small, reversible
  changes." Using the existing `urllib.request.urlopen` mock pattern keeps
  this batch consistent with `test_github_api_fetcher.py` and adds no new
  dependency.
- `tests/unit/test_repo_metadata_store_sqlite.py` (new): insert + read
  roundtrip, upsert overwrites, get on unknown repository_id returns `None`,
  distinct repositories are independent, `initialize()` is idempotent
  — mirroring `test_synopsis_store_sqlite.py`'s structure.
- `tests/unit/test_postgres_adapters.py` (extended): `PostgresRepoMetadataStore`
  roundtrip + upsert, gated by the existing
  `DATABASE_URL`-must-start-with-`postgresql`
  `pytestmark = pytest.mark.skipif(...)` already in that file — skipped
  locally, runs in CI only when a Postgres service is configured (same
  posture as every other Postgres adapter test in this repo).
- `tests/unit/test_api_mappers.py` or a new
  `tests/unit/test_repo_metadata_mapper.py`: `map_languages` — percent
  computation, rounding, empty input → `[]`, order preservation.
- `tests/unit/test_api_repos.py` (extended): `GET /api/repos` includes
  `stars`/`languages` fields; a repo with a stored metadata row returns
  populated values with correct percents; a repo with no metadata row returns
  `stars=None, languages=[]` (does not error, does not break the existing
  fast-path tests in this file, since `build_repo_metadata_store(...).initialize()`
  is a `CREATE TABLE IF NOT EXISTS`).

### Manual/e2e verification (Playwright, run by the orchestrator)

1. Ingest a repository with `GITHUB_TOKEN` set. Confirm the repo card shows a
   ⭐ star count and a language bar with a legend once ingestion completes.
2. Hover/focus each language segment and legend entry; confirm the tooltip
   (via the existing `data-tip`/`#global-tip` mechanism, not a native
   `title=`) shows `"<Language>: <percent>%"`.
3. Confirm a repository ingested with `GITHUB_TOKEN` unset (or a non-GitHub
   URL) shows neither the star badge nor the language bar, with no layout
   gap/placeholder.
4. Confirm dark and light themes both render the language bar with visibly
   distinct segment colors.

### Evaluation required

Not applicable — no LLM call is involved in this feature.

## 16. Documentation impact

- `docs/progress/api/batch-94-github-stars-languages.md` records this batch's
  work (filed under `api/`, matching batch 58's "GitHub context enrichment"
  precedent for GitHub-adjacent API/ingestion work, since this feature spans
  ingestion, storage, API, and frontend rather than living purely in the
  ingestion layer).
- `docs/progress/README.md` gets a new entry under `## API`.

## 17. ADR impact

None. This is an additive adapter + store + API field + frontend rendering
feature within the existing hexagonal layering (`infrastructure/github.py` for
the new adapter class, mirrored SQLite/Postgres stores wired through the
existing `composition.py` factory pattern) — no new architectural boundary is
introduced.

## 18. Open questions

- **Should stars/languages be refreshed periodically (not just at ingestion
  time)?** Assumption made: no — out of scope for this batch (see
  Non-goals). A repository's stars/language mix changes slowly; a future
  batch can add a refresh endpoint or scheduled job if staleness becomes a
  problem in practice.
- **Should a partial stars-fetch failure still allow a retry on next
  ingestion of the same repository?** Assumption made: yes, implicitly — since
  nothing is cached/negatively-cached (unlike `GithubContextCache`), a repeat
  ingestion of the same repository will simply attempt the fetch again. No
  explicit retry logic is added; this falls out of "no cache" by design.
- **Should the language bar cap at 8 segments + "Other"?** Assumption made:
  yes, driven by the dataviz-skill's categorical-palette non-negotiable ("a
  9th series is never a generated hue — it folds into Other"). Flagged as a
  deviation-from-nothing (the brief didn't specify a cap) but a necessary one
  to keep the palette accessible and CVD-safe.

## 19. Out of scope

- Fetching or displaying any other GitHub repository field (forks, open
  issues, license, topics, etc.) — only stars and languages.
- A metadata refresh/backfill endpoint or scheduled job.
- Changes to `GithubContextFetcher`/`GithubContext` (per-commit PR/issue
  enrichment).
- A JS unit-test framework (same investigated-and-confirmed absence as specs
  016/017/018).
