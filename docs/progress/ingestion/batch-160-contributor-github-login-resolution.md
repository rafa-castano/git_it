## Batch 160 — Contributor GitHub login resolution (profile links) (spec 031)

### Goal

Make a contributor card's "GitHub" link point at the person's real **profile**
(`github.com/{login}`) instead of a user search page. Until now the login was derived
purely from the commit author's email (`_extract_github_username`), which only succeeds
for GitHub **noreply** emails; an author who committed with an ordinary email had no login,
so `static/app.js` fell back to `github.com/search?q={name}`. Spec 031 resolves the real
login from the GitHub REST **List commits** endpoint — whose top-level `author` object
carries the matched account's `login`, paired with the git `commit.author.email` — stores
the `email → login` map per repository, and lets the existing contributor read model return
a real `github_username` with **no frontend change**.

### What was added

**Fetcher (`infrastructure/github.py`)**
- `GithubCommitAuthorsFetcher.fetch_author_logins(canonical_url, needed_emails) -> dict[str, str]`.
  Paginates `GET /repos/{owner}/{repo}/commits?per_page=100&page=N` (reusing the existing
  `_parse_owner_repo` + token/urllib plumbing), building `{commit.author.email: author.login}`
  only for commits whose top-level `author` is non-null **and** whose email is in
  `needed_emails`. Stops early once every needed email resolves, a short/empty page is seen,
  or `COMMIT_AUTHORS_MAX_PAGES` (env-backed, default 100) is reached. `token is None`, empty
  needed set, or non-GitHub URL → `{}` with no API call. Best-effort and failure-isolated:
  a mid-run HTTP/network/parse error returns whatever was resolved so far, logging the
  exception **type name only** (never the token or URL).
- `_is_valid_github_login` (`TypeGuard[str]`, `^[A-Za-z0-9-]{1,39}$`): a resolved login is
  untrusted API content, charset-validated before it is ever stored or used (AC-09).

**Port + adapters**
- `AuthorLoginStore` port (`application/ports.py`): `save_author_logins` / `get_author_logins`.
- `SqliteAuthorLoginStore` / `PostgresAuthorLoginStore` (new `sqlite/author_logins.py`,
  `postgres/author_logins.py`, exported from the package `__init__`s): table `author_logins`
  PK `(repository_id, author_email)`, `github_login TEXT NULL`. Upsert (idempotent re-save);
  a stored `NULL` is an "attempted, no match" marker so `null`-author emails are never
  re-queried. `get_author_logins` returns the full mapping including null markers, empty dict
  for an unknown repo. Both carry a `read_distinct_author_emails(repository_id)` convenience
  (distinct non-empty `commit_facts.author_email`) so the enrichment hook needs a single
  collaborator besides the fetcher. `migrations/001_initial.sql` gains the table.

**Enrichment hook (`api/routes/repos.py`)**
- `_fetch_and_store_commit_author_logins(...)`, wired into `_ingest_bg` after a COMPLETED
  ingest alongside the existing repo-metadata / discussion / release / advisory fetchers.
  Computes `needed = distinct_emails − already_attempted`; returns **without any API call**
  when needed is empty (AC-04) or the token is unset (AC-05); otherwise fetches and upserts
  the resolved logins **plus a `null` marker for every needed-but-unresolved email**.
  Failure-isolated: catches, logs type-name only, ingest still COMPLETED (AC-07). Because
  it lives only in `_ingest_bg`, **Refresh all** (which bypasses `_ingest_bg`) makes zero
  login-resolution calls by construction (AC-06).

**Contributor reader precedence (`sqlite/contributors.py` + Postgres mirror)**
- `list_contributors` now loads the repo's `author_email → login` map (its own connection,
  tolerating a missing `author_logins` table → empty map, so reads never provision tables)
  and sets `github_username = login_map.get(email) or _extract_github_username(email)`:
  a stored non-null login wins (AC-02); a stored-null or missing email falls through to the
  noreply heuristic, then `None` (AC-03). Frontend untouched — it already `esc()`s and
  `encodeURIComponent()`s `github_username`.

**Composition**
- `build_author_login_store(*, project_root)` (mirrors `build_repo_metadata_store`): SQLite
  gets `initialize()`; PostgreSQL relies on the migration.

### Tests added

- New `test_github_commit_authors_fetcher.py`: mapping, null-author skip, needed-restriction,
  early-stop (second page never fetched), pagination, no-token/empty-needed/non-GitHub → `{}`,
  HTTP error → empty, mid-run error → partial, malformed payload → empty, hostile login
  rejected + charset-validator table (AC-01/05/07/09).
- New `test_author_login_store_sqlite.py`: round-trip incl. null markers, empty-for-unknown,
  idempotent re-save overwriting a null marker, repo isolation, `read_distinct_author_emails`
  (dedupe, empty-email exclusion, repo scoping) (AC-08).
- Extended `test_postgres_adapters.py` (`DATABASE_URL`-gated): store round-trip + null markers
  + upsert, and contributor-reader stored-login precedence (AC-08/02).
- Extended `test_api_contributors.py`: stored login wins over noreply heuristic; stored login
  resolves a regular email; stored-null falls back to heuristic (AC-02/03).
- Extended `test_api_repos.py`: hook skips without token; skips the API when needed is empty;
  queries only the never-attempted email and preserves prior markers; stores a null marker for
  unresolved emails; failure-isolated; and a `RefreshAllService` run makes zero login calls
  (AC-04/05/06/07).
- Full unit suite green: **1238 passed, 40 skipped** (Postgres tests skipped without
  `DATABASE_URL`). `ruff check`, `ruff format --check`, and `mypy src/ <changed tests>` clean.

### Gotchas

- **`per_page=` contains the substring `page=`.** A naive `url.split("page=")` in a test helper
  parsed `per_page=100` as page 100 and served an empty page. Fixed the helper to split on
  `&page=`; the production URL builder was never affected.
- **Reads must not provision tables.** The contributor readers query `author_logins` in their
  own connection wrapped in `except OperationalError` / `except psycopg.Error → {}`, so a DB
  ingested before spec 031 (or a read-only caller) degrades to the heuristic instead of 500ing.
  The Postgres reader isolates this in a separate connection so a missing table can't abort the
  main contributor-stats transaction.
- **`or` precedence is exactly the spec's precedence.** `login_map.get(email) or heuristic(email)`
  works because a stored value is always a non-empty valid login or `NULL` — the charset
  validator (`+` quantifier) rejects empty strings, and unresolved emails are stored as `NULL`,
  both of which correctly fall through to the heuristic.

### Commits

- `feat: resolve contributor GitHub logins from List commits endpoint (spec 031)`
