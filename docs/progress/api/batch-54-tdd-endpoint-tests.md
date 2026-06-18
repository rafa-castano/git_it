## Batch 54 — TDD endpoint tests for API routes

### Goal

Write the missing characterization tests for all untested API endpoints, using the existing `test_api_repos.py` pattern. These tests form the safety net for the hexagonal architecture refactor in batch 55.

### What was added

**`tests/unit/test_api_contributors.py` — 11 tests:**
- `test_contributors_returns_404_when_db_missing`
- `test_contributors_returns_404_when_no_commits`
- `test_contributors_returns_commit_count_per_author`
- `test_contributors_is_bot_true_for_bot_suffix`
- `test_contributors_is_bot_false_for_human`
- `test_contributors_github_username_from_new_noreply_email`
- `test_contributors_github_username_from_old_noreply_email`
- `test_contributors_github_username_none_for_regular_email`
- `test_contributors_category_counts_from_analyses`
- `test_contributors_active_days_counts_distinct_days`
- `test_contributors_migration_guard_survives_existing_column`

**`tests/unit/test_api_analyze.py` — 18 tests:**

Estimate endpoint (4):
- `test_estimate_returns_404_when_db_missing`
- `test_estimate_returns_correct_counts`
- `test_estimate_cost_proportional_to_llm_calls`
- `test_estimate_zero_calls_when_all_analyzed`

Analyze POST (5):
- `test_analyze_returns_404_when_db_missing`
- `test_analyze_returns_analyzing_status`
- `test_analyze_rejects_non_anthropic_model`
- `test_analyze_requires_auth_when_api_key_set`
- `test_analyze_accepts_valid_auth`

Analyze status (4):
- `test_analyze_status_defaults_when_no_analysis_running`
- `test_analyze_status_returns_live_progress`
- `test_analyze_status_pct_zero_when_total_zero`
- `test_analyze_status_pct_100_when_complete`

Ingest (5):
- `test_ingest_returns_ingesting_status`
- `test_ingest_normalizes_shorthand_url`
- `test_ingest_rejects_invalid_url`
- `test_ingest_repository_id_is_deterministic`
- `test_ingest_requires_auth_when_api_key_set`

**Infrastructure:**
- `tests/__init__.py` and `tests/unit/__init__.py` created to enable cross-module imports
- `tests/unit/fakes.py` with canonical `FakeCommitReader` shared across all analysis test files

### Gotchas

- `commit_analyses.data` must be a fully valid `CommitAnalysis`-compatible JSON including lowercase `category` and `confidence` field — the estimate path calls `CommitAnalysis.model_validate_json` which validates the full schema
- `_analyze_progress` is a module-level dict; tests must import it from `git_it.api.routes.repos` and reset via monkeypatch
- `GIT_IT_API_KEY` is read from `os.environ` at request time; use `monkeypatch.setenv` in auth tests

### Commits

- `test: TDD endpoint tests for contributors, analyze, ingest, and status routes`
