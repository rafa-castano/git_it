## Batch 37 — Commit pre-classifier (skip/include/sample)

### Goal

Classify commits before any LLM call to eliminate noise and guarantee high-signal commits are always analyzed.

### Source of truth

- Cost optimization strategy: eliminate automated/bot commits from LLM budget

### Examples covered

- Skip: Dependabot bumps, merge commits, lock file updates, format-only, CI automation, Snyk, Renovate, release/changelog
- Include: `feat:/fix:/refactor:/perf:` conventional commits, breaking changes (`!` scope, `BREAKING CHANGE`), security/auth/migration keywords, reverts
- Sample: everything else (default LLM flow)
- Gotcha: `"fix: typo"` must NOT be `include` — typo check on first 20 chars of first line

### Tests added

- `tests/unit/test_commit_pre_classifier.py` — 31 tests
- `tests/unit/test_commit_analysis_service.py` — 4 wiring tests

### Production behavior added

- `application/pre_classifier.py` — `CommitPreClassification` dataclass, `CommitPreClassifier` (stateless, pure functions)
- `application/commit_analysis_service.py` — classifier called after cache check; `skip` → `continue` (no LLM, absent from results)

### Commits

- `da0b4b3 feat: add commit pre-classifier with skip and include rules`
- `9613f66 feat: wire pre-classifier into commit analysis service`
