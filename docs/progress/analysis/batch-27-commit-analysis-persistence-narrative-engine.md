## Batch 27 — CommitAnalysis persistence + narrative engine + case-study command

### Goal

Complete the MVP pipeline: persist structured commit analyses to SQLite (so LLM is not called repeatedly), implement the narrative engine that synthesizes analyses and hotspot data into an educational case study, and expose a `case-study` CLI command.

### Source of truth

- `docs/specs/002-commit-analysis.md` (persistence)
- `docs/specs/004-narrative-engine.md`

### Examples covered

- `SqliteCommitAnalysisStore`: INSERT OR IGNORE idempotency; JSON serialization via `model_dump_json()` / `model_validate_json()`; `get_analysis`, `list_analyses` with optional limit
- `CommitAnalysisService` caching: skips LLM call when analysis already in store; saves new analyses when writer provided; does not re-save cached analyses
- `NarrativeService`: empty analyses → returns empty result without LLM call; commit summaries + hotspot files included in prompt; data wrapped in `[REPOSITORY DATA]` tags (prompt injection); system prompt marks data as untrusted
- `case-study` CLI: exits 0; prints narrative; "No analyses" message when none; passes model to factory

### Tests added

- `tests/unit/test_sqlite_commit_analysis_store.py` — 7 tests
- `tests/unit/test_commit_analysis_service_cache.py` — 3 tests
- `tests/unit/test_narrative_service.py` — 7 tests
- `tests/unit/test_case_study_cli.py` — 4 tests

### Production behavior added

- `application/ports.py` — `CommitAnalysisWriter`, `CommitAnalysisReader` Protocols
- `infrastructure/sqlite.py` — `SqliteCommitAnalysisStore` (implements both protocols)
- `application/commit_analysis_service.py` — optional `analysis_writer` + `analysis_reader` params; cache-aware `analyze_commits`
- `application/narrative_service.py` — `NarrativeResult`, `NarrativeService` (reads analyses + file churn, calls LLM with untrusted-data-tagged prompt)
- `composition.py` — `build_commit_analysis_service` now wires `SqliteCommitAnalysisStore`; `build_narrative_service()`
- `interfaces/cli.py` — `case-study <url> [--model MODEL]` subcommand; `NarrativeFactory`, `NarrativeGeneratorService` protocols

### MVP status

The full pipeline is now wired:
1. `git-it ingest <url>` — clone/fetch repo, persist commit facts + file facts to SQLite
2. `git-it analyze-commits <url>` — per-commit structured analysis with caching
3. `git-it patterns <url>` — rule-based hotspot detection from file facts
4. `git-it case-study <url>` — narrative synthesis from stored analyses + hotspots

### Follow-up

- Add bugfix recurrence and refactor wave detectors (spec 003) that read from `commit_analyses`
- Improve narrative structure: timeline, architectural transitions, learning lessons
- Add `list analyses` CLI command to inspect stored analyses
