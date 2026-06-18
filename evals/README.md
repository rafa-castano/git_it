# Git It — Evaluation Harness

## What it measures

Accuracy of the LLM commit classifier against 20 hand-labeled commits.
Two dimensions are scored: **category** (feature, bugfix, refactor, test, docs, chore,
build, security, performance) and **risk level** (low, medium, high).

## How to run

```bash
uv run python evals/run.py
```

Options:

```
--model MODEL     LiteLLM model string  (default: anthropic/claude-haiku-4-5-20251001)
--fixture PATH    Path to golden_commits.json  (default: evals/golden_commits.json)
--output PATH     Write JSON report to this file in addition to stdout
--verbose         Print each commit message and the full predicted analysis
```

Requires `ANTHROPIC_API_KEY` (or the key for whichever provider you select).

## How to add new golden commits

Edit `evals/golden_commits.json` and append an object following this schema:

```json
{
  "sha": "<12-char hex string>",
  "message": "<commit message first line>",
  "author_name": "<Author Name>",
  "committed_at": "<ISO 8601 datetime>",
  "files_changed": ["path/to/file.py"],
  "expected_category": "<one of the CommitCategory enum values>",
  "expected_risk_level": "<low | medium | high>",
  "rationale": "<why this label is correct>"
}
```

Valid categories: `feature`, `bugfix`, `refactor`, `test`, `docs`,
`chore`, `build`, `security`, `performance`, `unknown`.

## Passing score

**75% combined** (average of category accuracy and risk accuracy).
Below 75% indicates model regression or prompt drift and should block a release.
