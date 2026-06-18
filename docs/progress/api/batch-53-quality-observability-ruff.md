## Batch 53 — Quality fixes, observability, and ruff compliance

### Goal

Address all findings from the quality agent review: code smells, ruff/UP042 violations, coverage gate, bare except, and logging gaps.

### What was added

**ruff / UP042 fixes:**
- `CommitCategory(str, enum.Enum)` → `CommitCategory(enum.StrEnum)`
- `RiskLevel(str, enum.Enum)` → `RiskLevel(enum.StrEnum)`

**Renamed `TestGrowthSignal` → `CommitTestGrowthSignal`:**
- Was triggering `PytestCollectionWarning` because pytest tried to collect it as a test class
- Renamed across domain, schemas, tests, and all references

**Code smells fixed:**
- `sqlite3.connect()` in `get_contributors` replaced with a context manager (`with sqlite3.connect(...) as con:`)
- Named constant `_LLM_COST_PER_CALL_USD = 0.0008` extracted from inline literal
- Bare `except Exception: pass` in schema migrations tightened to `except sqlite3.OperationalError as e: if "duplicate column name"/"already exists" not in str(e).lower(): raise`

**Observability:**
- `import logging` + `_logger = logging.getLogger(__name__)` added to `repos.py`, `commit_analysis_service.py`, and `llm.py`
- Background threads log ingestion/analysis lifecycle events (INFO)
- Per-commit DEBUG logs: `commit {sha[:8]}: cached / skipped / analyzing`
- Batch completion INFO: `analyzed={n} cached={n} skipped={n}`
- LLM adapter logs model, sha[:8], and duration for each call

**Typed API schemas:**
- `_dataclass_to_dict` helper removed from `repos.py`
- `PatternReportResponse` sub-fields replaced with 8 typed Pydantic schemas:
  `RefactorWaveSchema`, `RevertSignalSchema`, `CommitTestGrowthSignalSchema`, `BugfixRecurrenceSchema`, `OwnershipConcentrationSchema`, `DependencyMigrationSchema`, `ArchitecturalShiftSchema`, `PatternExplanationSchema`

**Coverage gate:**
- `pytest.ini` updated: `addopts = --cov=git_it --cov-report=term-missing`
- `.` added to `pythonpath` so `from tests.unit.fakes import ...` works

**Deduplicated test fakes:**
- `tests/unit/fakes.py` created with canonical `FakeCommitReader`
- All analysis test files now import from `tests.unit.fakes` instead of each defining their own

### Tests added

Several existing unit tests updated:
- `FakeCommitAnalysisClient.analyze_commit` signatures updated to `(system, messages)`
- Trivial `test_hotspot_is_a_dataclass_with_expected_fields` replaced with a meaningful behavior test

### Gotchas

- `TestGrowthSignal` is a domain class but pytest collects any class starting with `Test` — always use a non-Test prefix for domain classes
- `StrEnum` is only available from Python 3.11; this codebase requires 3.12+ so it's always safe

### Commits

- `refactor: quality fixes, StrEnum, observability logging, typed schemas, ruff compliance`
