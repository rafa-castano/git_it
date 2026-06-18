# Batch 61 — Evaluation Harness for LLM Commit Classification

## Goal

Add an objective, reproducible way to measure how accurately the LLM classifies commits
by category and risk level, against a hand-labeled golden fixture.

## What was built

### `evals/golden_commits.json`

20 labeled commits covering all 9 commit categories present in `CommitCategory`:
`feature` (3), `bugfix` (3), `refactor` (4), `test` (2), `docs` (2), `chore` (2),
`performance` (2), `security` (1), `build` (1).

Risk levels: low (9), medium (7), high (4).

Design decisions:
- Commit messages span Python, Java, TypeScript, and Go ecosystems for variety.
- One intentionally ambiguous case (`revert:` message that maps to `refactor` because
  the domain has no `revert` category — tests model behavior on edge inputs).
- All `parent_shas` are empty tuples so the pre-classifier never skips them as merge commits.
- Messages avoid patterns the pre-classifier would skip (no `bump X from Y to Z`, no
  `merge pull request #`, no `[skip ci]`) because `analyze_commit()` does not run the
  pre-classifier — but commits that would be pre-classified `skip` in production would
  never reach the LLM anyway, making them poor golden cases.

### `evals/run.py`

Standalone evaluation harness:
- Loads the fixture, constructs a `CommitRecord` per entry, calls
  `CommitAnalysisService.analyze_commit()` (the single-commit path, not `analyze_commits()`).
- Uses `InstructorCommitAnalysisAdapter` as the `CommitAnalysisClient`.
- Passes `_NoopCommitReader` as the `reader` — `analyze_commit()` does not use the reader,
  so no database is required.
- Detects missing API keys for known providers and exits with a clear error before making
  any LLM calls.
- Prints a structured report with per-category breakdown and failure list.
- Accepts `--output PATH` to write a machine-readable JSON report.

### `evals/README.md`

Under-30-line documentation: what is measured, how to run, how to extend, passing threshold.

## Key discovery: service API

`CommitAnalysisService` exposes `analyze_commit(commit, *, repo_context=...)` as the
single-commit entry point. It does NOT call `self._reader` — that is only used by
`analyze_commits()`. The `reader` constructor argument is still required positionally,
so a no-op stub satisfies the type contract without any production code changes.

The actual LLM client class is `InstructorCommitAnalysisAdapter` (in
`src/git_it/repository_ingestion/infrastructure/llm.py`), not `LiteLLMCommitAnalysisClient`
as referenced in the task brief.

## Files

- `evals/golden_commits.json` — 20 labeled golden commits
- `evals/run.py` — evaluation harness script
- `evals/README.md` — usage documentation
- `docs/progress/evals/batch-61-evaluation-harness.md` — this file
