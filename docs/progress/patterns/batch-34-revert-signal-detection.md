## Batch 34 — Revert signal pattern detection

### Goal

Detect instability via revert commit ratio as a signal of rework or broken workflows.

### Source of truth

- `docs/specs/003-pattern-detection.md`

### Examples covered

- Commit messages starting with `"revert"` (case-insensitive) counted
- `revert_ratio = revert_count / total_commit_count`
- Configurable `revert_threshold` (default: ratio ≥ 0.05)
- Uses `CommitSummaryRecord` reader to scan all commit messages without loading full analyses

### Tests added

- `tests/unit/test_revert_signal_detection.py` — 8 tests
- `tests/unit/test_sqlite_commit_summary_reader.py` — 4 tests

### Production behavior added

- `application/ports.py` — `CommitSummaryRecord`, `CommitSummaryReader` Protocol
- `domain/patterns.py` — `RevertSignal` frozen dataclass; `PatternReport.revert_signal`
- `application/pattern_detection_service.py` — optional `commit_summary_reader`; `_compute_revert_signal`
- `infrastructure/sqlite.py` — `SqliteCommitReader.list_commit_messages()`
- `composition.py` — wires `SqliteCommitReader` as `commit_summary_reader`
- `interfaces/cli.py` — `_print_pattern_report` shows revert signal
