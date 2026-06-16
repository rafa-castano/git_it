from pathlib import Path

import pytest

from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)
from git_it.repository_ingestion.interfaces.cli import main


def _make_analysis(sha: str = "abc1234", summary: str = "Added a feature") -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary=summary,
        category=CommitCategory.FEATURE,
        intent=None,
        intent_is_inferred=True,
        affected_components=["core"],
        risk_level=RiskLevel.LOW,
        confidence=0.7,
        evidence=[],
        limitations=[],
    )


class FakeCommitBatchService:
    def __init__(self, analyses: list[CommitAnalysis] | None = None) -> None:
        self._analyses = analyses or []
        self.calls: list[tuple[str, int | None]] = []

    def analyze_commits(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        self.calls.append((repository_id, limit))
        return self._analyses


def _factory(service: FakeCommitBatchService):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path, repository_id: str, model: str) -> FakeCommitBatchService:
        return service

    return factory


def test_analyze_commits_exits_zero(tmp_path: Path) -> None:
    service = FakeCommitBatchService(analyses=[_make_analysis()])
    code = main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert code == 0


def test_analyze_commits_shows_no_commits_when_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeCommitBatchService(analyses=[])
    main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    captured = capsys.readouterr()
    assert "No commits" in captured.out


def test_analyze_commits_prints_category_and_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeCommitBatchService(analyses=[_make_analysis(summary="Implement auth")])
    main(
        ["analyze-commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    captured = capsys.readouterr()
    assert "feature" in captured.out.lower()
    assert "Implement auth" in captured.out


def test_analyze_commits_passes_limit_to_service(tmp_path: Path) -> None:
    service = FakeCommitBatchService()
    main(
        ["analyze-commits", "https://github.com/owner/repo", "--limit", "3"],
        project_root=tmp_path,
        commit_analysis_factory=_factory(service),
    )
    assert service.calls[0][1] == 3
