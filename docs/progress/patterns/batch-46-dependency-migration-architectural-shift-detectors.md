## Batch 46 — Dependency migration and architectural shift detectors

### Goal

Add two new rule-based pattern detectors from spec 003 that were previously unimplemented: dependency migrations (library replacements detected from commit messages) and architectural shifts (top-level directory structure analysis).

### Examples covered

```text
Dependency Migrations:
  requests → httpx: 2 commits  [confidence: 67%]
    Evidence: a1b2c3d, e4f5g6h
    Period: 2024-03-01 → 2024-04-15

Architectural Shifts:
  [new_top_level_dir] Directory 'services/' contains 47 tracked files  [confidence: 1.00]
  [module_extraction] Multiple significant top-level modules detected  [confidence: 0.60]
```

### Tests added

- `tests/unit/test_dependency_migration_detector.py` — 10 tests (regex patterns, noise filtering, grouping, confidence, evidence SHAs)
- `tests/unit/test_architectural_shift_detector.py` — 6 tests (top-level dir threshold, single-dir skip, module extraction signal)
- 2 integration tests in `test_pattern_detection_service.py`

### Production behavior added

- `domain/patterns.py` — `DependencyMigration` and `ArchitecturalShift` frozen dataclasses; `PatternReport` gains `dependency_migrations` and `architectural_shifts` fields
- `application/pattern_detection_service.py` — `_compute_dependency_migrations()` (5 regex patterns: migrate/replace/switch/move from X to Y; noise filtering for short tokens and common words; confidence `min(1.0, count/3.0)`); `_compute_architectural_shifts()` (top-level dir file counts; module extraction signal when ≥3 dirs have ≥5 files each; skip when only 1 top-level dir); both wired into `detect()`; `_report_has_patterns()` updated
- `interfaces/cli.py` — two new output sections in `_print_pattern_report`

### Gotcha

The architectural shift detector skips output when only 1 top-level directory exists (no multi-module signal). Tests that exercise the "new top-level dir" path need at least 2 distinct top-level dirs in the file churn data.

### Commits

- `6b5a3c7 feat: add DependencyMigration and ArchitecturalShift domain models`
- `9b51968 feat: implement dependency migration and architectural shift detectors`

---
