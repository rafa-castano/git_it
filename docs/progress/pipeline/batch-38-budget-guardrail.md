## Batch 38 — Budget guardrail with `--yes` flag

### Goal

Show how many LLM calls will be made before running, and ask for confirmation when above a threshold.

### Source of truth

- Cost safety: prevent accidental large LLM runs

### Examples covered

```text
$ git-it run https://github.com/owner/repo
  143 commits will be sent to LLM.
143 LLM calls planned. Proceed? [y/N]
```

```text
$ git-it run https://github.com/owner/repo --yes   # skips confirmation
```

### Tests added

- `tests/unit/test_commit_analysis_estimate.py` — 8 tests
- `tests/unit/test_analyze_commits_cli.py` — 4 budget tests
- `tests/unit/test_pipeline_run_command.py` — 4 budget tests

### Production behavior added

- `application/commit_analysis_service.py` — `estimate_llm_calls(repository_id, *, limit)` method
- `interfaces/cli.py` — `CommitBatchService` Protocol gains `estimate_llm_calls`; `--yes` flag on `analyze-commits` and `run`; `budget_confirm_fn` and `budget_threshold` injectable params on `main()` (default threshold: 50)

### Gotchas

- mypy rejects `lambda n: (list.append(n), False)[1]` — use `def` instead
- `FakeCacheReader` must implement `list_analyses()` even if unused to satisfy Protocol structurally

### Commits

- `4fcb49e feat: add estimate_llm_calls to commit analysis service`
- `6ff3da6 feat: add budget guardrail with --yes flag`
