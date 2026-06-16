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


def test_no_refactor_wave_when_analysis_reader_absent() -> None:
    service = PatternDetectionService(reader=FakeFileFactReader())
    report = service.detect("repo-1")
    assert report.refactor_wave is None


def test_no_refactor_wave_when_refactor_commits_below_threshold() -> None:
    analyses = [
        _analysis("s1", CommitCategory.REFACTOR),
        _analysis("s2", CommitCategory.REFACTOR),
        _analysis("s3", CommitCategory.FEATURE),
    ]
    report = _service(analyses).detect("repo-1", refactor_wave_threshold=3)
    assert report.refactor_wave is None


def test_refactor_wave_detected_at_threshold() -> None:
    analyses = [
        _analysis("s1", CommitCategory.REFACTOR),
        _analysis("s2", CommitCategory.REFACTOR),
        _analysis("s3", CommitCategory.REFACTOR),
        _analysis("s4", CommitCategory.FEATURE),
    ]
    report = _service(analyses).detect("repo-1", refactor_wave_threshold=3)
    assert report.refactor_wave is not None
    assert report.refactor_wave.commit_count == 3


def test_refactor_wave_ratio_is_refactor_over_total() -> None:
    analyses = [
        _analysis("s1", CommitCategory.REFACTOR),
        _analysis("s2", CommitCategory.REFACTOR),
        _analysis("s3", CommitCategory.REFACTOR),
        _analysis("s4", CommitCategory.FEATURE),
        _analysis("s5", CommitCategory.FEATURE),
    ]
    report = _service(analyses).detect("repo-1", refactor_wave_threshold=3)
    assert report.refactor_wave is not None
    assert report.refactor_wave.refactor_ratio == 0.6


def test_no_refactor_wave_with_empty_analyses() -> None:
    report = _service([]).detect("repo-1")
    assert report.refactor_wave is None
