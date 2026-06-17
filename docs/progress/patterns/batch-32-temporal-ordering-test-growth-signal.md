## Batch 32 — Temporal narrative ordering and test growth signal

### Goal

Make the narrative engine present commits in chronological order (oldest → newest) and add a test growth signal pattern detector.

### Source of truth

- `specs/003-pattern-detection.md`
- `specs/004-narrative-engine.md`

### Examples covered

- Narrative now orders commits by `committed_at ASC` using a JOIN between `commit_analyses` and `commit_facts`
- Test growth signal: ratio of test commits to bugfix commits as a quality health indicator
- `TimestampedAnalysis` DTO carries `committed_at` alongside `CommitAnalysis`

### Tests added

- `tests/unit/test_sqlite_commit_analysis_store.py` — `list_analyses_with_dates` tests
- `tests/unit/test_narrative_service.py` — temporal ordering tests
- `tests/unit/test_test_growth_signal.py` — test growth signal detection tests

### Production behavior added

- `application/ports.py` — `TimestampedAnalysis`, `TemporalAnalysisReader` Protocol
- `infrastructure/sqlite.py` — `SqliteCommitAnalysisStore.list_analyses_with_dates()` with JOIN on `commit_facts`
- `domain/patterns.py` — `TestGrowthSignal` frozen dataclass; `PatternReport.test_growth_signal`
- `application/pattern_detection_service.py` — `_compute_test_growth_signal`
- `application/narrative_service.py` — uses `TemporalAnalysisReader` for chronological ordering
- `interfaces/cli.py` — `_print_pattern_report` shows test growth signal
