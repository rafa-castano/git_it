## Batch 108 — GitHub Discussions GraphQL fetcher (spec 022, slice 2)

### Goal

Implement `GithubDiscussionsFetcher`, the inline GraphQL fetcher for spec 022
(GitHub Discussions ingestion and narrative evidence). This is the second of
the spec-022 build slices — batch 107 laid the domain/persistence foundation;
this batch adds the class that turns a repository's Discussions into a
bounded, qualified, ranked `list[Discussion]`. The LLM summarizer and the
ingest-time wiring remain for later batches (fetcher → summarizer → narrative
→ wiring), matching the TDD order the spec mandates.

### Why

Spec 022 defines the qualify filter, ranking, and volume cap as locked
decisions; batch 107's domain shapes and stores are otherwise dead code until
something actually produces a `Discussion`. This batch is the load-bearing
network boundary: a fixed GraphQL query template, bounded pagination, and a
best-effort contract that never raises past ingestion — mirroring the
existing `GithubRepoMetadataFetcher` (spec 019) posture.

### What was added

**`infrastructure/github.py`** (extended — `GithubContextFetcher` and
`GithubRepoMetadataFetcher` untouched)
- Module-level config constants (env-var-backed, batch-74 convention):
  `DISCUSSION_MIN_ENGAGEMENT_SCORE` (default 5), `DISCUSSION_MIN_REPLY_COUNT`
  (default 3), `DISCUSSION_MAX_SUMMARIZED` (default 20), `DISCUSSION_PAGE_SIZE`
  (default 50), `DISCUSSION_MAX_PAGES` (default 10).
- `_DISCUSSIONS_QUERY` — a fixed, hardcoded GraphQL template; only `owner`,
  `repo`, `first`, and the pagination `cursor` are parameterized, all derived
  from Git It's own URL parsing (`_parse_owner_repo`, reused unmodified) or the
  prior page's `endCursor` — never from discussion content.
- `GithubDiscussionsFetcher(token).fetch_qualifying_discussions(canonical_url)
  -> list[Discussion]`:
  - No token / non-GitHub URL → `[]`, no HTTP call, logged at DEBUG.
  - POSTs to `https://api.github.com/graphql` via `urllib.request`, same
    `Bearer` header, `_TIMEOUT` (10s), and `User-Agent` conventions as the
    REST fetchers.
  - Paginates via `hasNextPage`/`endCursor`, hard-capped at
    `DISCUSSION_MAX_PAGES` requests.
  - Applies the locked qualify filter: `(category == "Q&A" AND
    answerChosenAt is not null)` OR `(upvote+reaction >=
    DISCUSSION_MIN_ENGAGEMENT_SCORE)` OR `(comment_count >=
    DISCUSSION_MIN_REPLY_COUNT)`.
  - Ranks qualifying discussions by composite score
    (`upvote_count + reaction_count + comment_count`) descending, ties broken
    by most-recent `updated_at`, and truncates to `DISCUSSION_MAX_SUMMARIZED`
    (20) before returning — the cap is applied in-process, before any future
    LLM call, per the spec's cost-bounding requirement.
  - Any GraphQL/HTTP/network/timeout/rate-limit error, or a malformed/
    unexpected payload shape (non-dict response, missing `data`/`repository`/
    `discussions`/`nodes`/`pageInfo` keys), is caught and logged at WARNING
    with `type(exc).__name__` only — the method never raises.

### Tests added

- `tests/unit/test_github_discussions_fetcher.py` (15 tests, mocking
  `urllib.request.urlopen`, mirroring `test_github_repo_metadata_fetcher.py`'s
  style): Q&A + accepted answer qualifies regardless of engagement; non-Q&A
  qualifies via upvote+reaction threshold; non-Q&A qualifies via reply-count
  threshold; low-engagement chatter is skipped; no-token → no HTTP call;
  non-GitHub URL → no HTTP call; GraphQL HTTP error / rate limit / network
  timeout → `[]`; malformed payload (missing keys, non-dict, invalid JSON) →
  `[]`; pagination stops at exactly `DISCUSSION_MAX_PAGES` (10) requests when
  `hasNextPage` is always true; 35 qualifying discussions are ranked by
  composite score descending and truncated to exactly the top 20; returned
  objects are `Discussion` instances carrying the mapped raw fields.

Full suite: **846 passed, 21 skipped** (was 831 passed / 21 skipped before
this batch; +15 passing fetcher tests, no regressions).

### Gotchas

- The GraphQL response shape is validated defensively at every nesting level
  (`data` → `repository` → `discussions` → `nodes`/`pageInfo`) because a
  malformed payload must degrade to `[]`, not raise — any `KeyError`/
  `TypeError`/`ValueError` while walking the parsed JSON is caught in
  `_fetch_page` and treated the same as an HTTP-level failure.
- Ranking ties are broken by comparing `updated_at` as the raw ISO-8601 string
  from GitHub's GraphQL response; lexicographic string ordering is equivalent
  to chronological ordering for that format, so no datetime parsing was
  needed.
- `answerChosenAt is not null` is read directly as `is_answered`; the
  `answer.body` field (only present when an answer exists) maps to
  `Discussion.answer_body`, consistent with spec 022's domain concepts.

### Commits

- `feat: add GitHub Discussions GraphQL fetcher (spec 022)`
