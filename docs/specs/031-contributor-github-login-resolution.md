# Spec 031: Contributor GitHub Login Resolution (Profile Links)

**Status:** Implemented
**Spec number:** 031
**Author:** Rafael Castaño
Owner: AI Development Flow Agent
Primary agent: Software Engineering Agent
Supporting agents: Architecture Agent, Security Agent, Quality Agent
Created: 2026-07-08
Updated: 2026-07-08

## 1. Summary

A contributor card's "GitHub" link points at the contributor's **profile**
(`https://github.com/{login}`) only when we already know their GitHub `login`.
Today the login is derived purely from the commit author's email
(`_extract_github_username`, `infrastructure/sqlite/_common.py:45`), which only
succeeds for GitHub **noreply** emails (`123+user@users.noreply.github.com`). A
contributor who committed with an ordinary email (`foo@gmail.com`) has no login,
so `static/app.js:2892-2894` falls back to a **user search**
(`github.com/search?q={name}&type=users`) instead of the real profile.

This spec resolves the real GitHub login for contributors by reading it from the
GitHub REST **List commits** endpoint — whose top-level `author` object carries
the matched account's `login`, paired with the git `commit.author.email`
(verified against the official REST schema: top-level `author` is
`Simple User | null` with a required `login`; `commit.author` carries
`name`/`email`; `per_page` max 100). The resolved `email → login` map is stored
per repository and consumed by the contributor read model, so the profile link
resolves whenever GitHub can match the author to an account. When GitHub cannot
(top-level `author` is `null`) or no token is present, the card degrades to the
existing search fallback — never a broken link.

## 2. Problem

Clicking a contributor's GitHub link usually lands on a search results page, not
the person's profile, because the login is only known for noreply-email authors.
The only reliable source of a git author's GitHub login is the GitHub API, which
Git It does not currently consult for this purpose.

## 3. Goals

- Resolve each contributor's GitHub `login` from the **List commits** endpoint
  (`GET /repos/{owner}/{repo}/commits`, `per_page=100`), mapping
  `commit.author.email → author.login` for commits whose top-level `author` is
  non-null.
- Persist the mapping per repository so the contributor read model returns a real
  `github_username`, making `static/app.js` link to the profile with **no
  frontend change** (it already builds `github.com/{login}` from `github_username`).
- Resolve **incrementally** (spec 030 spirit): only call the API for author
  emails **not yet attempted**; store a row per attempted email (login, or a
  recorded "no match" so `null`-author emails are never re-queried). "Refresh all"
  must incur **zero** login-resolution API calls (it bypasses the enrichment path).
- Degrade cleanly: no `GITHUB_TOKEN`, `null` top-level author, or unresolved email
  → `github_username` stays absent → the existing search fallback renders.

## 4. Non-goals

- **No per-commit `GET /commits/{sha}` calls.** Only the paginated list endpoint.
- **No change to `RefreshAllService`** or the free `svc.ingest()` path. Login
  resolution runs only in the `_ingest_bg` enrichment block (`api/routes/repos.py`),
  next to the existing repo-metadata / discussion / release / advisory fetchers —
  the same token-gated, best-effort, failure-isolated posture.
- **No retigger of already-attempted authors.** A stored "attempted, no match"
  marker prevents re-querying `null`-author emails on every re-Analyze.
- **No new GitHub dependency.** Reuse the existing `requests`/token plumbing in
  `infrastructure/github.py`.
- **No profile guarantee.** Authors GitHub cannot match keep the search fallback;
  this is expected, not a failure.

## 5. Users

- A learner browsing the Contributors tab who wants to open a contributor's real
  GitHub profile, not a search page.

## 6. User stories

- As a learner, when I click a contributor whose commits GitHub can match to an
  account, I land on their profile page.
- As a learner, when GitHub cannot match the author (or no token is configured),
  the link still works as a best-effort user search — nothing breaks.

## 7. Acceptance criteria

- **AC-01** Given a repository ingested with a `GITHUB_TOKEN`, when enrichment runs
  after a COMPLETED ingest, then `GithubCommitAuthorsFetcher.fetch_author_logins`
  is called and the resolved `email → login` pairs (top-level `author` non-null)
  are persisted for that `repository_id`.
- **AC-02** Given a stored login for a contributor's email, when
  `list_contributors` builds the `ContributorRecord`, then `github_username` is the
  stored login (the API result takes precedence over the noreply-email heuristic).
- **AC-03** Given no stored login for a contributor's email, when
  `list_contributors` builds the record, then `github_username` falls back to
  `_extract_github_username(email)`, then to `None` (frontend search fallback).
- **AC-04** Given an author email already attempted (row exists, login present or
  `null`), when enrichment runs again, then that email is **not** re-queried against
  the GitHub API (incremental; only never-attempted emails are fetched).
- **AC-05** Given `GITHUB_TOKEN` is unset, when enrichment runs, then no login
  resolution API call is made and contributor links behave exactly as today.
- **AC-06** Given a "Refresh all" run, then **zero** login-resolution API calls are
  made (the enrichment path is not on the refresh route).
- **AC-07** Given the GitHub API errors, times out, or returns unexpected shapes,
  then enrichment logs a sanitized message (type-name only, no token/URL) and the
  ingest still reports COMPLETED (best-effort, failure-isolated — same posture as
  the existing enrichment fetchers).
- **AC-08** The store round-trips: `save_author_logins` then `get_author_logins`
  returns the persisted mapping (including attempted-but-`null` markers) for both
  the SQLite and PostgreSQL adapters; unknown repository → empty mapping.
- **AC-09** A resolved `login` is treated as untrusted input: it is charset-validated
  before storage/use and rendered through the existing `esc()` / `encodeURIComponent`
  path, so a hostile login string cannot inject markup or an off-github URL.

## 8. Domain concepts

- **Author-login mapping**: per repository, `author_email → github_login | null`.
  `null` = "GitHub was asked and returned no matching account" (attempted, no match).
- **Attempted set**: author emails already present in the store (any login value);
  excluded from further API queries (incremental resolution).

## 9. Inputs and outputs

- **New fetcher** `GithubCommitAuthorsFetcher` (`infrastructure/github.py`):
  `fetch_author_logins(self, canonical_url: str, needed_emails: set[str]) -> dict[str, str]`.
  Paginates the List commits endpoint (`per_page=100`), returns `email → login` only
  for `needed_emails` whose commit has a non-null top-level `author`. Stops early once
  every needed email is resolved or pages are exhausted. `token is None` → `{}`.
- **New port + adapters** `AuthorLoginStore`:
  `save_author_logins(repository_id, mapping: dict[str, str | None])`,
  `get_author_logins(repository_id) -> dict[str, str | None]`.
  SQLite + Postgres, new table `author_logins` PK `(repository_id, author_email)`,
  `github_login TEXT NULL`. `migrations/001_initial.sql` gains the table.
- **New reader** for distinct author emails already stored in `commit_facts`
  (or reuse an existing query): needed to compute the "needed_emails" set. May be a
  small addition to a contributors/commit reader.
- **Enrichment hook** `_fetch_and_store_commit_author_logins(...)` in
  `api/routes/repos.py`, invoked in `_ingest_bg` after COMPLETED ingest, alongside
  the existing fetchers. Computes needed = (distinct commit_facts emails) −
  (already-attempted emails), skips the API entirely if empty, else fetches + upserts
  (persisting `null` for needed-but-unresolved emails as attempted markers).
- **Contributor reader change** (`SqliteContributorReader` + Postgres mirror):
  resolve `github_username` = stored login (if a non-null login is stored for the
  author's email) else `_extract_github_username(email)` else `None`.

## 10. Evidence requirements

- Not an LLM/narrative claim. The login is factual metadata from the GitHub API; the
  contributor card already labels it as the GitHub handle. No confidence/interpretation
  fields required.

## 11. Failure modes

- **No token** → skip resolution, search fallback (AC-05).
- **API error / rate limit / malformed payload** → sanitized log, ingest still
  COMPLETED (AC-07); emails simply stay unattempted and may resolve on a later ingest.
- **Top-level `author` null** → email recorded as attempted-`null`; search fallback;
  never re-queried (AC-04).
- **Store/DB error during enrichment** → isolated like the other enrichment fetchers;
  does not fail the ingest.

## 12. Security considerations

- `GITHUB_TOKEN` never logged; error logs are type-name only (reuse existing
  sanitization posture). Repo/commit content — including `login`, `email`, `name` —
  is untrusted input (CODEX §7). The resolved `login` is charset-validated
  (`^[A-Za-z0-9-]+$`, GitHub's own login charset) before storage/use; the contributor
  DTO is already rendered via `esc()` and the URL via `encodeURIComponent`
  (`static/app.js:2893-2895`), so a hostile value cannot break out into markup or a
  non-github origin (AC-09). No new external write surface; read-only GitHub calls.

## 13. Privacy considerations

- GitHub login and commit author email are already public in the analyzed public
  repository's history and API. No new personal data is collected beyond what the
  public repo exposes; nothing is sent externally except the read-only API request.

## 14. Observability

- Log (info) the counts: needed emails, resolved logins, attempted-null — counts only,
  no PII beyond aggregate numbers, no token/URL.

## 15. Tests required

- Unit: `GithubCommitAuthorsFetcher` with a mocked HTTP layer (respx/monkeypatch):
  maps `commit.author.email → author.login`; skips commits with `null` top-level
  author; restricts to `needed_emails`; stops early when all resolved; paginates;
  `token is None` → `{}`; sanitized handling on error.
- Unit: `AuthorLoginStore` SQLite round-trip (including `null` markers; empty for
  unknown repo). Postgres mirror, `DATABASE_URL`-gated (skips without it).
- Unit: `SqliteContributorReader` (+ Postgres) — `github_username` precedence:
  stored login > noreply-email heuristic > `None` (AC-02/AC-03).
- Unit: enrichment hook computes needed = distinct emails − attempted; skips the
  fetcher when needed is empty (AC-04) and when token is absent (AC-05); is
  failure-isolated (AC-07).
- Unit: refresh-all path performs zero login-resolution calls (AC-06) — assert the
  enrichment hook is not on `RefreshAllService`'s route (structural/spy test).
- Unit: login charset validation rejects a hostile login (AC-09).

## 16. Evaluation required

- None (no LLM prompt or output change).

## 17. Documentation impact

- `docs/architecture.md` roadmap: add spec 031 (Implemented on completion).
- `README.md` — Contributors note may mention profile links resolve with a token.
- `docs/progress/{ingestion|api}/batch-{N}-contributor-github-login-resolution.md`
  + README index entry.

## 18. ADR impact

- None expected. New driven port + fetcher follow the existing enrichment pattern
  (`GithubRepoMetadataFetcher` + `RepoMetadataStore`, spec 019) and composition seam.

## 19. Open questions

- None blocking. If the "distinct author emails" query is better placed on an existing
  reader vs a new one, that is an implementation choice resolved during apply.
