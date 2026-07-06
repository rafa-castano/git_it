## Batch 138 — GitHub Releases and Security Advisories REST fetchers (spec 026, slice 2)

### Goal

Implement `GithubReleasesFetcher` and `GithubSecurityAdvisoriesFetcher`, the
two REST fetchers for spec 026 (GitHub Releases and Security Advisories as
cited narrative evidence). This is the second of the spec-026 build slices —
batch 137 laid the domain foundation (`Release`/`SecurityAdvisory`/
`ReleaseEvidence`/`AdvisoryEvidence`); this batch adds the classes that turn a
repository's published releases and non-withdrawn security advisories into
bounded `list[Release]` / `list[SecurityAdvisory]`. The LLM summarizers, the
persistence stores, and the ingest-time wiring remain for later batches
(fetchers → summarizers → stores → wiring → narrative), matching the TDD order
the spec mandates.

### Why

Spec 026 locks the fetch-layer contract: draft releases and withdrawn
advisories are filtered before ever reaching a summarizer, both fetchers skip
entirely (no API call) when `GITHUB_TOKEN` is absent — a deliberate
consistency choice, not a technical requirement — and each is bounded by an
env-var-backed `*_MAX_SUMMARIZED` cap to bound per-ingestion LLM cost. Both
`Release` and `SecurityAdvisory` are otherwise dead code from batch 137 until
something actually produces them.

### What was added

**`infrastructure/github.py`** (extended — existing fetchers untouched)

- Module-level config constants (env-var-backed, batch-74 convention):
  `RELEASE_MAX_SUMMARIZED` (default 10), `ADVISORY_MAX_SUMMARIZED` (default
  10).
- `_api_get_list(url, token) -> list[dict[str, object]] | None` — a new
  module-level sibling to `GithubRepoMetadataFetcher._api_get_dict`, mirroring
  its exact `urllib.request` transport, `Bearer` header, `_TIMEOUT` (10s), and
  exception-handling tuple, but for endpoints returning a top-level JSON
  **array** rather than an object. Filters to dict elements only; returns
  `None` on HTTP/network/timeout/JSON-decode error or a non-array payload
  (logged at WARNING with `type(exc).__name__` only, never raises). Placed as
  a standalone function (not a method) since both new fetcher classes need it
  and `_fetch_issue_body` already established the "standalone helper taking
  `token` as a parameter" pattern in this file.
- `GithubReleasesFetcher(token).fetch_releases(canonical_url) -> list[Release]`:
  - No token / non-GitHub URL → `[]` (not `None` — the return type is a list),
    no HTTP call, logged at DEBUG.
  - `GET /repos/{owner}/{repo}/releases` via `_api_get_list`.
  - Skips any item with `draft: true`; **prereleases are included** (only
    `draft` is filtered, per spec 026's locked decision).
  - Structurally validates `tag_name`/`html_url` as required non-empty `str`;
    malformed items are skipped, never raise.
  - Truncates to the first `RELEASE_MAX_SUMMARIZED` (10) qualifying releases —
    GitHub's releases endpoint already returns newest-first, so no re-sorting
    is needed.
- `GithubSecurityAdvisoriesFetcher(token).fetch_advisories(canonical_url) ->
  list[SecurityAdvisory]`: the symmetric fetcher for
  `GET /repos/{owner}/{repo}/security-advisories`, skipping any item with a
  non-null `withdrawn_at`, structurally validating `ghsa_id`/`html_url`/
  `summary`/`description` as required non-empty `str`, truncating to
  `ADVISORY_MAX_SUMMARIZED` (10). `severity` is passed through as the raw
  string with no `Literal` validation here — that enforcement belongs to
  `AdvisoryEvidence`'s `field_validator` at summarization time (batch 139), per
  the spec's locked layering.
- `_parse_release` / `_parse_advisory` — module-level parsing helpers doing the
  field-mapping and structural validation described above.

### Tests added

- `tests/unit/test_github_releases_fetcher.py` (9 tests, mocking
  `urllib.request.urlopen`, mirroring `test_github_repo_metadata_fetcher.py`'s
  style): no-token → `[]` with no HTTP call; non-GitHub URL → `[]` with no HTTP
  call; happy path (2 releases, newest-first order preserved); draft excluded
  while non-draft prerelease is included; `RELEASE_MAX_SUMMARIZED` bound
  respected (patched to 2, 5 fed, first 2 kept); HTTP error → `[]`; non-array
  payload → `[]`; malformed item (empty `tag_name`, empty `html_url`) skipped
  while the valid item is kept; malformed JSON body → `[]`.
- `tests/unit/test_github_security_advisories_fetcher.py` (9 tests, symmetric
  set): no-token, non-GitHub URL, happy path (2 advisories), withdrawn
  advisory excluded, `ADVISORY_MAX_SUMMARIZED` bound respected, HTTP error,
  non-array payload, malformed item (empty `ghsa_id`/`summary`) skipped, and
  malformed JSON body — all graceful, never raise.

Full suite: **1030 passed, 27 skipped** (was 1012 passed / 27 skipped before
this batch; +18 passing fetcher tests, no regressions).

### Gotchas

- `_api_get_list` had to be a new function rather than reusing
  `_api_get_dict` — the releases/security-advisories endpoints return a
  top-level JSON array, and `_api_get_dict`'s `isinstance(raw, dict)` check
  would reject that payload shape outright.
- The MAX-bound tests patch the module-level constant directly
  (`patch("git_it...infrastructure.github.RELEASE_MAX_SUMMARIZED", 2)`) rather
  than the environment variable, since the constant is read once at import
  time — this mirrors how the constant is referenced by name (not via
  `os.environ.get` at call time) inside `fetch_releases`/`fetch_advisories`.
- `severity` is deliberately *not* validated against the `low`/`medium`/
  `high`/`critical` enum in the fetcher — only `AdvisoryEvidence`'s
  `field_validator` enforces that, at summarization time. The fetcher passes
  the raw GitHub value through so an out-of-range advisory API oddity is
  something the summarizer layer's schema validation catches and drops. No
  breaking behavior yet exists between the two layers since the summarizer
  lands in batch 139.

### Commits

- `feat: add GitHub Releases and Security Advisories REST fetchers (spec 026)`
