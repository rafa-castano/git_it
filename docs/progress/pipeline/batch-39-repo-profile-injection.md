## Batch 39 — Repo profile injection

### Goal

Inject the existing case study narrative as background context into the system prompt for each commit analysis, so the LLM categorizes commits knowing the project's domain without re-analyzing everything.

### Source of truth

- Quality improvement: context-aware commit categorization

### Examples covered

- First run (no case study): no context injected
- Second run (case study exists): first 2000 chars of narrative injected as `## Repository Background` in system prompt
- Context fetched once per `analyze_commits()` batch, passed to every LLM call

### Tests added

- `tests/unit/test_commit_analysis_repo_context.py` — 9 tests
- `tests/unit/test_sqlite_case_study_store.py` — 2 new tests

### Production behavior added

- `application/ports.py` — `RepoContextReader` Protocol
- `infrastructure/sqlite.py` — `SqliteCaseStudyStore.get_repo_context()` returns `narrative[:2000]`; constant `_REPO_CONTEXT_MAX_CHARS = 2000`
- `application/commit_analysis_service.py` — `repo_context_reader` param; `_build_messages` gains `repo_context` kwarg; sentinel pattern to avoid double reader call
- `composition.py` — `build_commit_analysis_service` wires `SqliteCaseStudyStore` as `repo_context_reader`

### Gotcha

Sentinel pattern (`_SENTINEL = object()`) in `analyze_commit()` distinguishes "no context passed" (consult reader) from "explicit `None`" (skip reader), preventing double fetch when `analyze_commits()` pre-fetches.

### Commits

- `09baa09 feat: add RepoContextReader port and get_repo_context to SqliteCaseStudyStore`
- `830c49c feat: inject repo context into commit analysis system prompt`
