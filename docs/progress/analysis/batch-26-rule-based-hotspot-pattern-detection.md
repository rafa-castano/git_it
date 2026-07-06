## Batch 26 — rule-based hotspot pattern detection (spec 003)

### Goal

Implement the first pattern detector: hotspot detection using aggregated file change data already stored in `file_facts`. No LLM required — pure SQL aggregation.

### Source of truth

- `docs/specs/003-pattern-detection.md` (layer 1: rule-based detectors)

### Examples covered

- Files changed in N or more distinct commits are classified as hotspots
- Hotspots sorted by `commit_count` descending
- `churn = total_insertions + total_deletions`
- Results isolated by `repository_id`
- Empty result when no file facts stored

### Tests added

- `tests/unit/test_pattern_detection_service.py` — 8 tests (threshold, sorting, churn, empty repo, repo isolation via reader)
- `tests/unit/test_sqlite_file_fact_reader.py` — 5 tests (aggregation, distinct commit count, repo isolation, sort order)
- `tests/unit/test_patterns_cli.py` — 4 tests (exit code, no-data message, output content, threshold forwarding)

### Production behavior added

- `domain/patterns.py` — `Hotspot` (frozen dataclass with `churn` property), `PatternReport`
- `application/ports.py` — `FileChurnRecord`, `FileFactReader` Protocol
- `application/pattern_detection_service.py` — `PatternDetectionService.detect(hotspot_threshold=5)`
- `infrastructure/sqlite.py` — `SqliteFileFactReader` with GROUP BY + COUNT(DISTINCT commit_sha) query
- `composition.py` — `build_pattern_detection_service()`
- `interfaces/cli.py` — `patterns <url> [--hotspot-threshold N]` subcommand

### Follow-up

Next patterns to add: bugfix recurrence (multiple bugfix CommitAnalyses for same component) and refactor wave (cluster of refactor commits in a time window). These require stored CommitAnalysis records.
