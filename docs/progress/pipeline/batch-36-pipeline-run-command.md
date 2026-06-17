## Batch 36 — Pipeline run command

### Goal

Add `git-it run <url>` to execute the full pipeline (ingest → analyze-commits → case-study) in a single command.

### Source of truth

- MVP usability requirement

### Examples covered

```text
$ git-it run https://github.com/owner/repo
Ingesting...
Ingestion status: COMPLETED
Commits: 946 inserted, 0 reused
Files: 4368 inserted, 0 reused
Analyzing commits...
Analyzed 10 commits.
Generating case study...
Case Study (10 commits, 3 hotspot files)
...
```

With flags: `--model`, `--limit`, `--force`

### Tests added

- `tests/unit/test_pipeline_run_command.py` — 15 tests covering happy path, step invocation, progress output, limit/force/model forwarding, ingestion failure abort

### Production behavior added

- `interfaces/cli.py` — `run` subparser with `--model`, `--limit`, `--force`; `_run_pipeline` orchestrates the three steps; aborts with exit 1 if ingestion fails
