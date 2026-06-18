## Batch 58 — GitHub context enrichment (PR and issue injection into commit analysis)

### Goal

Enrich the LLM prompt used for commit analysis with structured data fetched from the GitHub API: the pull request description and linked issue bodies associated with each commit. Data is cached in SQLite to avoid repeated API calls. When no `GITHUB_TOKEN` is present, enrichment is silently skipped and all behaviour is identical to the previous version.

### What was added

**New domain type** (`domain/github_context.py`):
- `GithubContext` — frozen dataclass holding `pr_number`, `pr_title`, `pr_body`, `issue_numbers`, `issue_bodies`, `has_pr`.

**New port** (`application/ports.py`):
- `GithubContextReader` Protocol — `get_github_context(*, repository_id, canonical_url, commit_sha) -> GithubContext | None`.
- `GithubContext` and `GithubContextReader` added to `__all__`.

**New infrastructure** (`infrastructure/github.py`):
- `GithubContextFetcher` — checks cache first; on miss, calls `GET /repos/{owner}/{repo}/commits/{sha}/pulls` with `Accept: application/vnd.github+json`; fetches up to 3 linked issue bodies; saves result to cache; returns `GithubContext | None`.
- Graceful degradation: 429/403 → skip, no cache write; 401 → skip, no cache write; network error → skip, no cache write; 404/empty array → write negative cache entry.
- Uses `urllib.request` only — zero new dependencies.

**Extended SQLite adapter** (`infrastructure/sqlite.py`):
- `SqliteGithubContextCache` — new class with `initialize()`, `is_cached()`, `get_cached()`, `save()`.
- Table `github_context (repository_id, commit_sha, pr_number, pr_title, pr_body, issue_numbers, issue_bodies, has_github_data, fetched_at)`.
- `INSERT OR IGNORE` prevents duplicates on repeated analysis runs.

**Service changes** (`application/commit_analysis_service.py`):
- `CommitAnalysisService.__init__` gains `github_context_reader: GithubContextReader | None = None`.
- `analyze_commits()` and `analyze_commits_async()` gain `canonical_url: str | None = None`.
- `_analyze_with_client` fetches github context per commit when reader and canonical_url are set.
- `_build_messages` gains `github_context: GithubContext | None = None`; renders `[GITHUB CONTEXT — UNTRUSTED USER-GENERATED CONTENT FROM PULL REQUEST AND ISSUES]` block between `[REPO CONTEXT]` and `[REPOSITORY DATA]`.
- PR body truncated at 1000 chars; issue bodies truncated at 500 chars; max 3 issues rendered.
- `_SYSTEM_PROMPT` extended with instruction to treat `[GITHUB CONTEXT]` as untrusted data.

**Composition** (`composition.py`):
- `build_commit_analysis_service` reads `GITHUB_TOKEN` from environment; if set, creates `SqliteGithubContextCache` + `GithubContextFetcher` and wires them as `github_context_reader`.

**Route changes** (`api/routes/repos.py`):
- `_resolve_canonical_url` helper looks up canonical URL from ingestion run store.
- `_analyze_bg` calls `_resolve_canonical_url` and passes result as `canonical_url` to `analyze_commits`.

**Test fakes** (`tests/unit/fakes.py`):
- `FakeGithubContextReader(context_map: dict[str, GithubContext | None])` — keyed by commit SHA.

### Tests added

| File | Count | What is tested |
|---|---|---|
| `test_github_context_cache.py` | 5 | `SqliteGithubContextCache`: table creation, cache miss, negative entry, positive entry, idempotent save |
| `test_github_api_fetcher.py` | 9 | `GithubContextFetcher`: no token, cache hit, no PR (negative cache), PR found (positive cache), 429, 403, 401, network timeout, issue fetch failure |
| `test_github_context_prompt.py` | 8 | `_build_messages`: no block when context None, no block when reader None, block present, untrusted tag, PR body truncation, issue body truncation, max 3 issues, block ordering |
| `test_commit_analysis_github_integration.py` | 4 | Service wiring: per-commit calls, canonical_url threading, None canonical_url skips reader, backward compatibility without reader |

**Total**: 26 new tests. Suite: 520 → 546.

### Gotchas

- `find("REPOSITORY DATA")` in ordering tests would match the substring inside the `[REPO CONTEXT — ... UNTRUSTED REPOSITORY DATA]` header. Fixed by searching for `[REPOSITORY DATA]` with brackets.
- `prs[0].get(...)` returns `object` in mypy because `_api_get` returned `object`. Fixed by typing return as `list[dict[str, object]]` and using `str()` casts.
- The groot preview header (`application/vnd.github.groot-preview+json`) for the commits-to-PRs endpoint is no longer required. The standard `application/vnd.github+json` header works as of current GitHub API docs.

### Commits

- `feat: enrich commit analysis with GitHub PR and issue context`
