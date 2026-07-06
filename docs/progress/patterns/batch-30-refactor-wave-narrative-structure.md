## Batch 30 — Refactor wave detection and spec 004 narrative structure

### Goal

Add refactor wave pattern detector and align narrative system prompt to spec 004 section structure.

### Source of truth

- `docs/specs/003-pattern-detection.md`
- `docs/specs/004-narrative-engine.md`

### Examples covered

- Refactor wave detected when REFACTOR commits >= threshold (default 3); reports count and ratio
- System prompt now requests: Overview → Timeline → Main Components Through Time → Key Mistakes and Corrections → Architectural Transitions → Engineering Lessons → Evidence Index → Limitations
- Refactor wave included in narrative LLM context as "Refactor Wave Detected" section

### Tests added

- `tests/unit/test_refactor_wave_detection.py` — 5 tests
- `tests/unit/test_narrative_service.py` — 3 new tests (refactor wave in prompt, spec 004 sections, category distribution in prompt)

### Production behavior added

- `domain/patterns.py` — `RefactorWave` frozen dataclass; `PatternReport.refactor_wave` field
- `application/pattern_detection_service.py` — `_compute_refactor_wave`, `refactor_wave_threshold` param on `detect()`
- `application/narrative_service.py` — spec 004 system prompt; refactor wave section in user message
- `interfaces/cli.py` — `_print_pattern_report` shows refactor wave

### Known limitation

Refactor wave is a global count, not temporal clustering. A true wave would require joining `commit_analyses` with `commit_facts.committed_at`. Tracked for future improvement.
