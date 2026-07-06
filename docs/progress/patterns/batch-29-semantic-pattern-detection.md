## Batch 29 — Semantic pattern detection

### Goal

Extend `PatternDetectionService` with semantic patterns derived from stored `CommitAnalysis` records: category distribution and bugfix-prone components.

### Source of truth

- `docs/specs/003-pattern-detection.md`

### Examples covered

- Category distribution: counts commits per `CommitCategory`, sorted by frequency
- Bugfix recurrence: components appearing in 2+ BUGFIX commits (uses `affected_components` from `CommitAnalysis`)
- `PatternDetectionService` accepts optional `analysis_reader`; falls back to pure churn detection when absent
- `NarrativeService._build_user_message` now receives full `PatternReport` and includes category counts and bugfix recurrences in LLM context

### Tests added

- `tests/unit/test_semantic_pattern_detection.py` — 7 tests

### Production behavior added

- `domain/patterns.py` — `CategoryCount`, `BugfixRecurrence` frozen dataclasses; `PatternReport` extended with `category_counts`, `bugfix_recurrences`
- `application/pattern_detection_service.py` — optional `analysis_reader`; `_compute_category_counts`, `_compute_bugfix_recurrences`
- `application/narrative_service.py` — `_build_user_message` takes full `PatternReport`; adds Category Distribution and Bugfix-Prone Components sections
- `composition.py` — `build_pattern_detection_service` wires `SqliteCommitAnalysisStore` as `analysis_reader`
- `interfaces/cli.py` — `_print_pattern_report` shows category counts and bugfix-prone components
