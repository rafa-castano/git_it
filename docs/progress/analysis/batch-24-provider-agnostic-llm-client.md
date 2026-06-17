## Batch 24 — Provider-agnostic LLM client and `git-it analyze` command

### Goal

Add a provider-agnostic LLM abstraction and the first working end-to-end analysis command. A user who has run `git-it ingest <url>` can now run `git-it analyze <url>` to get an AI-generated case study from the ingested commit history.

### Source of truth

- `specs/002-commit-analysis.md` — commit analysis goals and security requirements
- `litellm` is already in `pyproject.toml` — single adapter for all providers
- Security requirement: commit messages must be treated as untrusted data (prompt injection protection)

### Examples

```text
$ git-it analyze https://github.com/owner/repo
Analysis (47 commits)
============================================================
## Summary
This repository implements a REST API with progressive feature additions...

## Key Technical Decisions
- Moved from synchronous to async request handling in batch 3...
```

With a different model:

```text
$ git-it analyze --model openai/gpt-4o-mini https://github.com/owner/repo
$ git-it analyze --model gemini/gemini-1.5-flash https://github.com/owner/repo
$ git-it analyze --model ollama/llama3.2 https://github.com/owner/repo
```

With commit limit:

```text
$ git-it analyze --limit 100 https://github.com/owner/repo
```

No commits stored:

```text
No commits stored for this repository. Run 'git-it ingest <url>' first.
```

### Tests

New `tests/unit/test_repository_analysis_service.py`:

- `test_analysis_service_calls_llm_with_commit_data` — sha, message, and author appear in LLM call.
- `test_analysis_service_returns_analysis_result` — `AnalysisResult` with correct `commit_count` and `analysis`.
- `test_analysis_service_passes_limit_to_reader` — limit propagated.
- `test_analysis_service_returns_empty_result_when_no_commits_stored` — no LLM call when zero commits.
- `test_analysis_service_system_prompt_marks_commit_data_as_untrusted` — system message contains "untrusted"/"user input"/"user data".
- `test_analysis_service_commit_messages_appear_only_in_data_section` — malicious message inside `[REPOSITORY DATA]` tags in user message.

New `tests/unit/test_analyze_cli.py`:

- `test_analyze_cli_prints_analysis_text`
- `test_analyze_cli_shows_commit_count`
- `test_analyze_cli_shows_no_commits_message_when_count_is_zero`
- `test_analyze_cli_passes_model_flag_to_factory`
- `test_analyze_cli_passes_limit_to_service`

### Production behavior

Added `LLMMessage` frozen dataclass and `LLMClient` protocol to `application/ports.py`.

New `application/analysis_service.py`:

- `AnalysisResult` frozen dataclass (repository_id, commit_count, analysis).
- `RepositoryAnalysisService` with `analyze(repository_id, *, limit=50)`.
- System prompt marks all `[REPOSITORY DATA]` as untrusted user input (prompt injection protection).
- Builds user message with commit shas, dates, authors, first-line messages — all within `[REPOSITORY DATA]` / `[/REPOSITORY DATA]` tags.
- Returns empty `AnalysisResult` without calling LLM when no commits are found.

New `infrastructure/llm.py`:

- `LiteLLMLLMClient` — wraps `litellm.completion()`.
- `litellm` import is deferred inside `complete()` to avoid import-time side effects.
- Model string follows LiteLLM format: `anthropic/claude-haiku-4-5-20251001`, `openai/gpt-4o-mini`, `gemini/gemini-1.5-flash`, `ollama/llama3.2`, etc.

Updated `composition.py`:

- Added `build_repository_analysis_service(*, project_root, model, llm_client=None)`.

Updated `interfaces/cli.py`:

- Added `analyze` subparser with `--model` (default: `anthropic/claude-haiku-4-5-20251001`) and `--limit` (default: 50).
- Added `AnalysisFactory` protocol and `_default_analysis_factory`.
- `main` gains `analysis_factory` injectable parameter.
- `_run_analyze` and `_print_analysis_result` helpers.

### Follow-up

The next batch can add structured `CommitAnalysis` output (per spec 002 schema) using Pydantic + instructor, or begin pattern detection (spec 003) over the stored commit and file facts.
