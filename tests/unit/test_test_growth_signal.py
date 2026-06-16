from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
)
from git_it.repository_ingestion.application.ports import FileChurnRecord
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)


def _analysis(sha: str, category: CommitCategory) -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="summary",
        category=category,
        confidence=0.8,
        risk_level=RiskLevel.LOW,
        intent=None,
        intent_is_inferred=False,
        affected_components=[],
        evidence=[],
        limitations=[],
    )


class FakeFileFactReader:
    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        return []


class FakeAnalysisReader:
    def __init__(self, analyses: list[CommitAnalysis]) -> None:
        self._analyses = analyses

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        return list(self._analyses)

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        return None


def _service(analyses: list[CommitAnalysis]) -> PatternDetectionService:
    return PatternDetectionService(
        reader=FakeFileFactReader(),
        analysis_reader=FakeAnalysisReader(analyses),
    )


def test_no_signal_when_analysis_reader_absent() -> None:
    service = PatternDetectionService(reader=FakeFileFactReader())
    assert service.detect("repo-1").test_growth_signal is None


def test_no_signal_when_no_bugfix_commits() -> None:
    analyses = [_analysis("s1", CommitCategory.FEATURE)]
    assert _service(analyses).detect("repo-1").test_growth_signal is None


def test_no_signal_when_no_test_commits() -> None:
    analyses = [_analysis("s1", CommitCategory.BUGFIX)]
    assert _service(analyses).detect("repo-1").test_growth_signal is None


def test_signal_detected_with_test_and_bugfix_commits() -> None:
    analyses = [
        _analysis("s1", CommitCategory.BUGFIX),
        _analysis("s2", CommitCategory.TEST),
    ]
    signal = _service(analyses).detect("repo-1").test_growth_signal
    assert signal is not None
    assert signal.test_commit_count == 1
    assert signal.bugfix_commit_count == 1


def test_signal_ratio_is_test_over_bugfix() -> None:
    analyses = [
        _analysis("s1", CommitCategory.BUGFIX),
        _analysis("s2", CommitCategory.BUGFIX),
        _analysis("s3", CommitCategory.TEST),
    ]
    signal = _service(analyses).detect("repo-1").test_growth_signal
    assert signal is not None
    assert signal.test_to_bugfix_ratio == 0.5
