# Batch 94 — GitHub stars + language breakdown (spec 019)

## Goal

Show a repository's GitHub star count and language composition on its home-screen
card, fetched once at ingestion time (best-effort, degrading silently when
`GITHUB_TOKEN` is unset, the URL isn't GitHub, or the GitHub API call fails) and
persisted independently of the existing per-commit `GithubContextFetcher`
(PR/issue enrichment).

## Changes Made

### Domain (`src/git_it/repository_ingestion/domain/repo_metadata.py`, new)

- `LanguageBreakdown(language: str, bytes: int)` and
  `RepoMetadata(stars: int, languages: tuple[LanguageBreakdown, ...] = ())` — frozen
  dataclasses.

### Infrastructure — GitHub adapter (`infrastructure/github.py`)

- New `GithubRepoMetadataFetcher` class, alongside (not a modification of) the
  existing `GithubContextFetcher`. Reuses the same `urllib.request` transport,
  `Bearer` token header, 10s timeout, and `_parse_owner_repo` helper.
- `GET /repos/{owner}/{repo}` for `stargazers_count`; `GET
  /repos/{owner}/{repo}/languages` for the language map. Each field is
  structurally validated (int, non-bool, non-negative) before being trusted —
  the GitHub JSON is treated as untrusted input per ADR 008/CODEX.md.
- No cache — called at most once per ingestion, unlike the per-commit
  `GithubContextCache`.

### Infrastructure — stores (`infrastructure/sqlite.py`, `infrastructure/postgres.py`)

- `SqliteRepoMetadataStore` / `PostgresRepoMetadataStore`: one upserted row per
  repository in a new `repo_metadata` table
  (`repository_id PK, stars INTEGER, languages TEXT (JSON array), updated_at`).
- Both repository deleters (`SqliteRepositoryDeleter`, `PostgresRepositoryDeleter`)
  updated to also purge `repo_metadata` on repo deletion.
- `migrations/001_initial.sql` — `repo_metadata` table added for Postgres.

### Composition (`composition.py`)

- `build_repo_metadata_store(*, project_root)` — mirrors `build_case_study_store`'s
  backend-aware pattern (SQLite: constructs + `.initialize()`; Postgres: assumes
  schema already provisioned by the ingestion path).

### API (`api/schemas.py`, `api/mappers.py`, `api/routes/repos.py`)

- `LanguageItem(language, bytes, percent)`; `RepoSummary` gained
  `stars: int | None = None` and `languages: list[LanguageItem] = []`.
- `map_languages(languages) -> list[LanguageItem]` — pure function, `percent =
  round(bytes/total*100, 1)`, returns `[]` for empty input (no division by zero).
- `_fetch_and_store_repo_metadata(...)` — new helper called from `_ingest_bg` only
  when `RepositoryIngestionService.ingest()` returned `status == "COMPLETED"`.
  Never raises (broad `except Exception`, logged by type name only).
- `GET /api/repos` reads `repo_metadata` per repository (best-effort N+1 lookup —
  acceptable at current repo-list scale; flagged as a possible future
  optimization) and populates `stars`/`languages`, defaulting to `None`/`[]` when
  no row exists (pre-existing repos, token absent at ingestion time).

### Frontend (`static/app.js`, `static/app.css`)

- `_buildRepoCard` renders a `⭐ <stars>` badge (via the existing `data-tip`
  tooltip mechanism, not a native `title=`) and, when `languages` is non-empty, a
  horizontal stacked language bar (`_buildLanguageBar`) plus a text legend below
  it (language name + percent). Both render nothing when the corresponding field
  is absent — no layout break, no placeholder.
- Languages beyond the 8th (by byte count) fold into a trailing "Other" segment
  rendered in `var(--muted)`, never a 9th generated hue.
- New CSS custom properties `--lang-1`..`--lang-8` (dark and light steps) — a
  **dedicated** categorical palette for this bar, not a reuse of
  `--blue/--green/--red/...`. Those six already carry fixed status meaning
  elsewhere (green=completed, red=delete/error, yellow=in-progress) and would
  mislabel an arbitrary language; they also fail the dataviz skill's categorical
  palette checks outright (lightness-band FAIL on 3 of 6 hues) when run through
  `validate_palette.js`. The new 8-slot palette (dataviz skill's validated
  reference set) passes all checks against this app's actual `--surface` values
  in both themes, with only a CVD-adjacency floor-band `WARN` — mitigated by the
  always-present legend per the skill's relief rule.

## Files Changed

- `docs/specs/019-github-stars-languages.md` — new spec (Accepted)
- `src/git_it/repository_ingestion/domain/repo_metadata.py` — new
- `src/git_it/repository_ingestion/infrastructure/github.py` — `GithubRepoMetadataFetcher`
- `src/git_it/repository_ingestion/infrastructure/sqlite.py` — `SqliteRepoMetadataStore` + deleter update
- `src/git_it/repository_ingestion/infrastructure/postgres.py` — `PostgresRepoMetadataStore` + deleter update
- `migrations/001_initial.sql` — `repo_metadata` table
- `src/git_it/repository_ingestion/composition.py` — `build_repo_metadata_store`
- `src/git_it/api/schemas.py` — `LanguageItem`, `RepoSummary.stars`/`.languages`
- `src/git_it/api/mappers.py` — `map_languages`
- `src/git_it/api/routes/repos.py` — `_fetch_and_store_repo_metadata`, `_ingest_bg` and `list_repos` wiring
- `src/git_it/static/app.js` — `_buildLanguageBar`, `_buildRepoCard` stars/language rendering
- `src/git_it/static/app.css` — `--lang-1..8` custom properties, `.rc-lang-*` rules
- `tests/unit/test_github_repo_metadata_fetcher.py` — new (11 tests)
- `tests/unit/test_repo_metadata_store_sqlite.py` — new (6 tests)
- `tests/unit/test_repo_metadata_mapper.py` — new (4 tests)
- `tests/unit/test_postgres_adapters.py` — 3 new tests (skipped without live Postgres)
- `tests/unit/test_api_repos.py` — 5 new tests (stars/languages fields, ingestion-time fetch helper)
- `docs/progress/api/batch-94-github-stars-languages.md` — this file
- `docs/progress/README.md` — new entry in API section

## Tests Added

40 new tests (26 unconditional + 3 Postgres-gated skipped locally + the
remainder split as below):

- `test_github_repo_metadata_fetcher.py` (11): no-token skip, non-GitHub-URL
  skip, happy path, stars HTTP error / malformed JSON / non-dict JSON / missing
  `stargazers_count` (all → `None`), languages HTTP error (stars kept, empty
  languages), malformed language entries dropped, empty/non-dict languages
  payload.
- `test_repo_metadata_store_sqlite.py` (6): roundtrip, empty languages, upsert
  overwrite, cross-repo independence, `initialize()` idempotency, absent-row
  read.
- `test_repo_metadata_mapper.py` (4): empty input, percent computation, order
  preservation, rounding.
- `test_postgres_adapters.py` (+3, skipped without `DATABASE_URL`): absent read,
  roundtrip, upsert.
- `test_api_repos.py` (+5): no-metadata defaults, populated stars/languages
  through the full route, `_fetch_and_store_repo_metadata` token-absent skip /
  store-on-success / no-op-on-`None`.

Full suite: 774 passed, 15 skipped (was 748 passed / 12 skipped before this
batch — 26 new unconditional tests + 3 new Postgres-gated tests).

## Gotchas

- **The brief asked for `respx`-mocked HTTP; deviated.** Investigated and
  confirmed `github.py` uses stdlib `urllib.request`, not `httpx`, and neither
  `httpx` nor `respx` are dependencies anywhere in `pyproject.toml`. `respx`
  mocks `httpx` transports specifically — it cannot intercept `urllib`.
  Introducing `httpx`/`respx` into one adapter would fork the GitHub-HTTP
  transport across two libraries and add a new runtime dependency purely for a
  testing preference. Used the same `unittest.mock.patch("urllib.request.urlopen")`
  pattern already established by `test_github_api_fetcher.py`.
- **Fetch is orchestrated at the route layer, not inside
  `RepositoryIngestionService`.** That service is a pure git-mining pipeline
  with no GitHub API knowledge today; adding one HTTP-calling dependency to it
  for this one field would widen its responsibility. `_ingest_bg` in
  `api/routes/repos.py` already owns "things that happen once, after a
  successful ingest" (mirrors how `_analyze_bg` triggers narrative generation
  after analysis) — so the metadata fetch lives there instead.
- **Asymmetric failure handling (locked design decision):** a failed *stars*
  fetch voids the whole `RepoMetadata` result (nothing persisted); a failed
  *languages* fetch only empties that one field, keeping the stars value. Stars
  is the headline field; languages is additive polish.
- **N+1 read on `GET /api/repos`:** one `get_repo_metadata` call per listed
  repository. Acceptable at current scale (this endpoint already has a
  regression test guarding against a much worse fan-out bug in the commit-count
  subqueries); flagged in the spec as a possible future optimization (a single
  bulk read) if repo counts grow large enough to matter.
- **Backfill gap accepted, not solved:** a repository ingested before this
  batch has no `repo_metadata` row and is indistinguishable, from the API's
  point of view, from "token was absent at ingestion time" — both return
  `stars=None, languages=[]`. No backfill job is included (documented as a
  non-goal in the spec).
- **Language-bar palette is deliberately NOT the app's existing
  `--blue/--green/--red/...` set** — see spec 019 § Domain concepts and the
  Frontend section above for the validated-palette rationale.
- **JS test framework:** none exists in this repo (confirmed absence, same as
  specs 016/017/018) — `node --check src/git_it/static/app.js` is the only
  automated frontend gate; manual/e2e verification steps are listed in the spec.

## Commits

- (recorded in the batch commit for this file)
