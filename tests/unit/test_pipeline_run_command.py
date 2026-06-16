from dataclasses import dataclass
from pathlib import Path

import pytest

from git_it.repository_ingestion.application.narrative_service import NarrativeResult
from git_it.repository_ingestion.application.service import IngestionResult
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.interfaces.cli import main

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeIngestionService:
    result: IngestionResult
    calls: list[str]

    def ingest(self, raw_url: str) -> IngestionResult:
        self.calls.append(raw_url)
        return self.result


class FakeCommitBatchService:
    def __init__(self, analyses: list[CommitAnalysis] | None = None, estimate: int = 0) -> None:
        self._analyses = analyses or []
        self._estimate = estimate
        self.calls: list[tuple[str, int | None]] = []

    def analyze_commits(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        self.calls.append((repository_id, limit))
        return self._analyses

    def estimate_llm_calls(self, repository_id: str, *, limit: int | None = None) -> int:
        return self._estimate


class FakeNarrativeService:
    def __init__(self, result: NarrativeResult | None = None) -> None:
        self._result = result or NarrativeResult(
            repository_id="repo-1",
            commit_count=5,
            hotspot_count=2,
            narrative="Educational case study.",
        )
        self.calls: list[tuple[str, bool]] = []

    def generate(self, repository_id: str, *, force: bool = False) -> NarrativeResult:
        self.calls.append((repository_id, force))
        return self._result


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _ok_ingestion_result() -> IngestionResult:
    return IngestionResult(
        status="COMPLETED",
        error_code=None,
        stage="COMPLETED",
        retryable=False,
        safe_message=None,
        commits_inserted=3,
        commits_reused=0,
    )


def _failed_ingestion_result() -> IngestionResult:
    return IngestionResult(
        status="FAILED_VALIDATION",
        error_code="INVALID_URL",
        stage="VALIDATING_URL",
        retryable=False,
        safe_message="Repository URL must be a public GitHub HTTPS repository URL.",
    )


def _make_analysis(sha: str = "abc1234") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="Added a feature",
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.7,
        evidence=[],
        limitations=[],
    )


def _ingest_factory(service: FakeIngestionService):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path, repository_id: str) -> FakeIngestionService:
        return service

    return factory


def _commit_analysis_factory(service: FakeCommitBatchService):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path, repository_id: str, model: str) -> FakeCommitBatchService:
        return service

    return factory


def _narrative_factory(service: FakeNarrativeService):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path, repository_id: str, model: str) -> FakeNarrativeService:
        return service

    return factory


# ---------------------------------------------------------------------------
# Tests: run command — happy path
# ---------------------------------------------------------------------------


def test_run_exits_zero_on_success(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService()

    code = main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    assert code == 0


def test_run_invokes_all_three_steps(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    assert ingest_svc.calls == ["https://github.com/owner/repo"]
    assert len(commit_svc.calls) == 1
    assert len(narrative_svc.calls) == 1


def test_run_prints_progress_for_each_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    out = capsys.readouterr().out
    assert "Ingesting" in out
    assert "Analyzing commits" in out
    assert "Generating case study" in out


def test_run_prints_ingestion_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    out = capsys.readouterr().out
    assert "COMPLETED" in out


def test_run_prints_commit_analysis_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    analyses = [_make_analysis("abc1234"), _make_analysis("def5678")]
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=analyses)
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    out = capsys.readouterr().out
    assert "2" in out


def test_run_prints_narrative_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService(
        result=NarrativeResult(
            repository_id="repo-1",
            commit_count=1,
            hotspot_count=0,
            narrative="Strong TDD culture.",
        )
    )

    main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    out = capsys.readouterr().out
    assert "Strong TDD culture." in out


# ---------------------------------------------------------------------------
# Tests: --limit passes through to analyze-commits step only
# ---------------------------------------------------------------------------


def test_run_passes_limit_to_commit_analysis_step(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo", "--limit", "7"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    assert commit_svc.calls[0][1] == 7


def test_run_does_not_pass_limit_to_narrative_step(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo", "--limit", "7"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    # generate() is called once; force defaults to False (limit is irrelevant)
    assert narrative_svc.calls[0][1] is False


# ---------------------------------------------------------------------------
# Tests: --force passes through to case-study step
# ---------------------------------------------------------------------------


def test_run_passes_force_false_by_default(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    assert narrative_svc.calls[0][1] is False


def test_run_passes_force_true_when_flag_given(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo", "--force"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    assert narrative_svc.calls[0][1] is True


# ---------------------------------------------------------------------------
# Tests: --model passes through to both LLM steps
# ---------------------------------------------------------------------------


def test_run_passes_model_to_commit_analysis_factory(tmp_path: Path) -> None:
    received_models: list[str] = []

    def commit_factory(
        *, project_root: Path, repository_id: str, model: str
    ) -> FakeCommitBatchService:
        received_models.append(model)
        return FakeCommitBatchService(analyses=[_make_analysis()])

    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "https://github.com/owner/repo", "--model", "openai/gpt-4o-mini"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=commit_factory,
        narrative_factory=_narrative_factory(narrative_svc),
    )

    assert received_models == ["openai/gpt-4o-mini"]


def test_run_passes_model_to_narrative_factory(tmp_path: Path) -> None:
    received_models: list[str] = []

    def narr_factory(*, project_root: Path, repository_id: str, model: str) -> FakeNarrativeService:
        received_models.append(model)
        return FakeNarrativeService()

    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()])

    main(
        ["run", "https://github.com/owner/repo", "--model", "openai/gpt-4o-mini"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=narr_factory,
    )

    assert received_models == ["openai/gpt-4o-mini"]


# ---------------------------------------------------------------------------
# Tests: ingestion failure aborts the pipeline
# ---------------------------------------------------------------------------


def test_run_returns_exit_code_1_when_ingestion_fails(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_failed_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService()
    narrative_svc = FakeNarrativeService()

    code = main(
        ["run", "not-a-url"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    assert code == 1


def test_run_skips_subsequent_steps_when_ingestion_fails(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_failed_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService()
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "not-a-url"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    assert commit_svc.calls == []
    assert narrative_svc.calls == []


def test_run_prints_failure_message_when_ingestion_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ingest_svc = FakeIngestionService(result=_failed_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService()
    narrative_svc = FakeNarrativeService()

    main(
        ["run", "not-a-url"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
    )

    out = capsys.readouterr().out
    assert "Ingestion failed" in out


# ---------------------------------------------------------------------------
# Tests: budget guardrail for run command
# ---------------------------------------------------------------------------


def test_run_yes_flag_skips_budget_confirmation(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()], estimate=999)
    narrative_svc = FakeNarrativeService()
    confirm_called: list[int] = []

    def _confirm(n: int) -> bool:
        confirm_called.append(n)
        return False  # would abort if called

    code = main(
        ["run", "https://github.com/owner/repo", "--yes"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
        budget_confirm_fn=_confirm,
        budget_threshold=10,
    )

    assert code == 0
    assert confirm_called == []


def test_run_aborts_when_budget_exceeded_and_not_confirmed(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()], estimate=100)
    narrative_svc = FakeNarrativeService()

    code = main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
        budget_confirm_fn=lambda n: False,
        budget_threshold=10,
    )

    assert code == 1
    assert commit_svc.calls == []


def test_run_proceeds_when_budget_confirmed(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()], estimate=100)
    narrative_svc = FakeNarrativeService()

    code = main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
        budget_confirm_fn=lambda n: True,
        budget_threshold=10,
    )

    assert code == 0
    assert len(commit_svc.calls) == 1


def test_run_no_confirmation_when_under_threshold(tmp_path: Path) -> None:
    ingest_svc = FakeIngestionService(result=_ok_ingestion_result(), calls=[])
    commit_svc = FakeCommitBatchService(analyses=[_make_analysis()], estimate=5)
    narrative_svc = FakeNarrativeService()
    confirm_called: list[int] = []

    def _confirm(n: int) -> bool:
        confirm_called.append(n)
        return True

    main(
        ["run", "https://github.com/owner/repo"],
        project_root=tmp_path,
        service_factory=_ingest_factory(ingest_svc),
        commit_analysis_factory=_commit_analysis_factory(commit_svc),
        narrative_factory=_narrative_factory(narrative_svc),
        budget_confirm_fn=_confirm,
        budget_threshold=10,
    )

    assert confirm_called == []
