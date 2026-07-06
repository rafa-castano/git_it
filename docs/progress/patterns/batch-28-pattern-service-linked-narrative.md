## Batch 28 — Pattern service linked into narrative engine

### Goal

Make `case-study` and `patterns` consume the same hotspot data: same threshold, same ordering, same source of truth.

### Source of truth

- `docs/specs/004-narrative-engine.md`

### Examples covered

- `NarrativeService` now calls `pattern_service.detect()` (via `HotspotDetector` Protocol) instead of reading raw file churn directly
- `hotspot_count` in `NarrativeResult` now reflects files above threshold, not total files with any churn

### Tests added / updated

- `tests/unit/test_narrative_service.py` — replaced `FakeFileFactReader` with `FakePatternService`; added `test_generate_calls_pattern_service_detect`, `test_generate_hotspot_count_reflects_pattern_report`

### Production behavior added

- `application/narrative_service.py` — replaced `file_fact_reader` dependency with `pattern_service: HotspotDetector` Protocol
- `composition.py` — `build_narrative_service` wires `build_pattern_detection_service` output
