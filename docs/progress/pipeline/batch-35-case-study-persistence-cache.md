## Batch 35 — Case study persistence and cache

### Goal

Cache generated case studies in SQLite so repeated `case-study` calls skip the LLM.

### Source of truth

- `specs/004-narrative-engine.md`

### Examples covered

- First call generates and stores; second call returns cached without LLM
- `--force` flag bypasses cache and regenerates
- `CaseStudyRecord` fields: `repository_id`, `narrative`, `commit_count`, `hotspot_count`
- UPSERT on conflict (not INSERT OR IGNORE) so regeneration overwrites stale data

### Tests added

- `tests/unit/test_case_study_persistence.py` — 6 tests
- `tests/unit/test_sqlite_case_study_store.py` — 4 tests

### Production behavior added

- `application/ports.py` — `CaseStudyRecord`, `CaseStudyStore` Protocol
- `infrastructure/sqlite.py` — `SqliteCaseStudyStore` with `case_studies` table; UPSERT on conflict
- `application/narrative_service.py` — optional `case_study_store`; cache check before LLM call; `force: bool = False` param on `generate()`
- `composition.py` — `build_narrative_service` wires `SqliteCaseStudyStore`
- `interfaces/cli.py` — `case-study` gains `--force` flag; `NarrativeGeneratorService` Protocol updated
