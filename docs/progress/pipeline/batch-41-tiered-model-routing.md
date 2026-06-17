## Batch 41 — Tiered model routing

### Goal

Route commit analysis to different LLM models based on the pre-classifier tier: `include`-tier commits (feat/fix/refactor/breaking/security) go to the primary (premium) model; `sample`-tier commits (everything else that isn't skipped) go to a cheaper/faster model. This allows users to configure e.g. `--model anthropic/claude-sonnet-4-6 --sample-model anthropic/claude-haiku-4-5-20251001`.

### Source of truth

Pre-classifier tier decisions from Batch 37 (`CommitPreClassifier`). LiteLLM model string convention already established.

### Examples covered

```text
$ git-it run https://github.com/owner/repo \
    --model anthropic/claude-sonnet-4-6 \
    --sample-model anthropic/claude-haiku-4-5-20251001

$ git-it analyze-commits https://github.com/owner/repo \
    --sample-model ollama/llama3.2
```

### Tests added

- `tests/unit/test_commit_analysis_tiered_models.py` — 6 tests (routing logic: include→primary, sample→sample_client, fallback when no sample_client, public `analyze_commit()` always uses primary, mixed batch, skip goes to neither)
- New `--sample-model` CLI tests in `test_analyze_commits_cli.py` and `test_pipeline_run_command.py`

### Production behavior added

- `application/commit_analysis_service.py` — `sample_client: CommitAnalysisClient | None = None` constructor param; `_analyze_with_client(client, commit, *, repo_context)` private method; `analyze_commits()` selects `sample_client` when tier is `"sample"` and sample_client is configured
- `composition.py` — `build_commit_analysis_service()` gains `sample_model: str | None = None`; creates `InstructorCommitAnalysisAdapter(model=sample_model)` only when `sample_model` differs from `model`
- `interfaces/cli.py` — `CommitAnalysisFactory` Protocol updated; `--sample-model` added to `analyze-commits` and `run`; forwarded through `_run_analyze_commits` and `_run_pipeline`

### Design note

When `sample_model == model` (or omitted), `sample_client` is `None` — the service falls through to `self._client` for both tiers. No wasted adapter instance. The public `analyze_commit()` single-commit method always uses the primary client — tiered routing only applies inside the `analyze_commits()` batch loop.

### Commits

- `29ff240 feat: add sample_client to commit analysis service for tiered model routing`
- `b4556db feat: add --sample-model flag and wire tiered model routing`

---
