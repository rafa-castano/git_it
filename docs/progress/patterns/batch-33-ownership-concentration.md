## Batch 33 — Ownership concentration pattern detection

### Goal

Detect knowledge silos: files touched by very few authors relative to their commit count.

### Source of truth

- `docs/specs/003-pattern-detection.md`

### Examples covered

- File with 20 commits but only 1 author → ownership concentration (knowledge silo risk)
- Configurable `ownership_threshold` (default: author_count ≤ 2)
- JOIN between `file_facts` and `commit_facts` to count distinct authors per file

### Tests added

- `tests/unit/test_ownership_concentration.py` — 7 tests
- `tests/unit/test_sqlite_ownership_reader.py` — 4 tests

### Production behavior added

- `application/ports.py` — `FileOwnershipRecord`, `OwnershipReader` Protocol
- `domain/patterns.py` — `OwnershipConcentration` frozen dataclass; `PatternReport.ownership_concentrations`
- `application/pattern_detection_service.py` — optional `ownership_reader`; `_compute_ownership_concentrations`
- `infrastructure/sqlite.py` — `SqliteFileFactReader.get_file_ownership()` with JOIN query
- `composition.py` — wires `SqliteFileFactReader` as `ownership_reader`
- `interfaces/cli.py` — `_print_pattern_report` shows ownership concentrations
