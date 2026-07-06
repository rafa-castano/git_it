## Batch 25 — structured per-commit analysis (spec 002)

### Goal

Implement `CommitAnalysis` domain model and `CommitAnalysisService` that produces structured, evidence-grounded per-commit interpretations using `instructor` + `litellm`.

### Source of truth

- `docs/specs/002-commit-analysis.md`

### Examples covered

- `CommitCategory` enum: feature, bugfix, refactor, test, docs, build, security, performance, chore, unknown
- `RiskLevel` enum: low, medium, high, unknown
- `confidence` validated as float in [0.0, 1.0] by Pydantic `Field(ge=0.0, le=1.0)`
- `EvidenceRef` with optional `file_path` and `quote`
- Prompt injection: commit messages wrapped in `[REPOSITORY DATA]` / `[/REPOSITORY DATA]`; system prompt marks them as untrusted

### Tests added

- `tests/unit/test_commit_analysis_domain.py` — 7 tests (schema validation, enum coverage, confidence bounds)
- `tests/unit/test_commit_analysis_service.py` — 7 tests (LLM call count, message content, REPOSITORY tags, untrusted data marking, result forwarding, batch behavior)
- `tests/unit/test_analyze_commits_cli.py` — 4 tests (exit code, no-commits message, output content, limit forwarding)

### Production behavior added

- `domain/analysis.py` — `CommitCategory`, `RiskLevel`, `EvidenceRef`, `CommitAnalysis` Pydantic model
- `application/ports.py` — `CommitAnalysisClient` Protocol
- `application/commit_analysis_service.py` — `CommitAnalysisService` with `analyze_commit` and `analyze_commits` methods
- `infrastructure/llm.py` — `InstructorCommitAnalysisAdapter` using `instructor.from_litellm`
- `composition.py` — `build_commit_analysis_service()`
- `interfaces/cli.py` — `analyze-commits <url> [--model MODEL] [--limit N]` subcommand

### Follow-up

Pattern detection (spec 003) can now consume `CommitAnalysis` records. Consider persisting analyses to SQLite for reuse before pattern detection runs.
