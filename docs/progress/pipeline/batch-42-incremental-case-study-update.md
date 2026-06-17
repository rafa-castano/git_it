## Batch 42 — Incremental case study update

### Goal

When a case study already exists for a repository, regenerate it using only the *new* commit analyses (those added after the case study was last generated) combined with the existing narrative as context. If there are no new analyses, return the existing case study without any LLM call.

### Source of truth

Both `commit_analyses` and `case_studies` tables already had `created_at` columns — timestamp-based approach (Option A) required no schema migration.

### Examples covered

```text
# First run — no existing case study — all 47 analyses sent to LLM
$ git-it run https://github.com/owner/repo

# Second run — 3 new commits since last run — only 3 analyses + existing narrative sent
$ git-it run https://github.com/owner/repo

# Third run — no new commits — LLM skipped entirely, existing case study returned
$ git-it run https://github.com/owner/repo
```

### Tests added

- `tests/unit/test_case_study_incremental.py` — 15 new TDD tests covering: full generation (no existing), incremental delta (new analyses only), skip LLM (no new analyses), prompt structure verification for both paths

### Production behavior added

- `application/ports.py` — `CaseStudyRecord` gains `generated_at: str | None = None`; new `TemporalAnalysisReader` Protocol with `list_analyses_since(repository_id, *, since: str)`
- `infrastructure/sqlite.py` — `SqliteCommitAnalysisStore.list_analyses_since()` filters by `created_at > since`; `SqliteCaseStudyStore.get_case_study()` returns `created_at` as `generated_at`
- `application/narrative_service.py` — `generate()` refactored into `_generate_full()` + `_generate_incremental()`; incremental path uses `_INCREMENTAL_SYSTEM_PROMPT` + "Existing Case Study" + "New Commits to Incorporate" sections in user message

### Gotcha

Legacy `CaseStudyRecord` instances without `generated_at` (value `None`) cause `_resolve_new_analyses()` to return `[]`, which correctly falls through to the existing cached record — backward-compatible behaviour for records written before this batch.

### Commits

- `eb230c3 feat: add incremental analysis query support`
- `f12c3f4 feat: implement incremental case study update`

---
