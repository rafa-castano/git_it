from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
)
from git_it.repository_ingestion.application.ports import FileChurnRecord
from git_it.repository_ingestion.domain.analysis import (
    CommitAnalysis,
    CommitCategory,
    RiskLevel,
)


def _analysis(
    sha: str,
    category: CommitCategory,
    components: list[str] | None = None,
) -> CommitAnalysis:
    return CommitAnalysis(
        commit_sha=sha,
        summary="summary",
        category=category,
        confidence=0.8,
        risk_level=RiskLevel.LOW,
        intent=None,
        intent_is_inferred=False,
        affected_components=components or [],
        evidence=[],
        limitations=[],
    )


class FakeFileFactReader:
    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        return []


class FakeAnalysisReader:
    def __init__(self, analyses: list[CommitAnalysis] | None = None) -> None:
        self._analyses = analyses or []

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        return list(self._analyses)

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        return None


def test_detect_without_analysis_reader_returns_empty_semantic_patterns() -> None:
    service = PatternDetectionService(reader=FakeFileFactReader())
    report = service.detect("repo-1")
    assert report.category_counts == []
    assert report.bugfix_recurrences == []


def test_detect_computes_category_distribution() -> None:
    analyses = [
        _analysis("sha1", CommitCategory.FEATURE),
        _analysis("sha2", CommitCategory.FEATURE),
        _analysis("sha3", CommitCategory.BUGFIX),
    ]
    service = PatternDetectionService(
        reader=FakeFileFactReader(),
        analysis_reader=FakeAnalysisReader(analyses),
    )
    report = service.detect("repo-1")
    counts = {cc.category: cc.count for cc in report.category_counts}
    assert counts["feature"] == 2
    assert counts["bugfix"] == 1


def test_category_counts_sorted_by_count_descending() -> None:
    analyses = [
        _analysis("s1", CommitCategory.BUGFIX),
        _analysis("s2", CommitCategory.FEATURE),
        _analysis("s3", CommitCategory.FEATURE),
        _analysis("s4", CommitCategory.FEATURE),
    ]
    service = PatternDetectionService(
        reader=FakeFileFactReader(),
        analysis_reader=FakeAnalysisReader(analyses),
    )
    report = service.detect("repo-1")
    assert report.category_counts[0].category == "feature"
    assert report.category_counts[0].count == 3


def test_detect_identifies_bugfix_recurrent_component() -> None:
    analyses = [
        _analysis("s1", CommitCategory.BUGFIX, ["auth"]),
        _analysis("s2", CommitCategory.BUGFIX, ["auth"]),
    ]
    service = PatternDetectionService(
        reader=FakeFileFactReader(),
        analysis_reader=FakeAnalysisReader(analyses),
    )
    report = service.detect("repo-1", bugfix_recurrence_threshold=2)
    assert len(report.bugfix_recurrences) == 1
    assert report.bugfix_recurrences[0].component == "auth"
    assert report.bugfix_recurrences[0].bugfix_commit_count == 2


def test_detect_excludes_component_below_recurrence_threshold() -> None:
    analyses = [_analysis("s1", CommitCategory.BUGFIX, ["auth"])]
    service = PatternDetectionService(
        reader=FakeFileFactReader(),
        analysis_reader=FakeAnalysisReader(analyses),
    )
    report = service.detect("repo-1", bugfix_recurrence_threshold=2)
    assert report.bugfix_recurrences == []


def test_non_bugfix_commits_do_not_count_toward_recurrence() -> None:
    analyses = [
        _analysis("s1", CommitCategory.FEATURE, ["auth"]),
        _analysis("s2", CommitCategory.FEATURE, ["auth"]),
        _analysis("s3", CommitCategory.BUGFIX, ["auth"]),
    ]
    service = PatternDetectionService(
        reader=FakeFileFactReader(),
        analysis_reader=FakeAnalysisReader(analyses),
    )
    report = service.detect("repo-1", bugfix_recurrence_threshold=2)
    assert report.bugfix_recurrences == []


def test_bugfix_recurrences_sorted_by_count_descending() -> None:
    analyses = [
        _analysis("s1", CommitCategory.BUGFIX, ["auth", "db"]),
        _analysis("s2", CommitCategory.BUGFIX, ["auth"]),
        _analysis("s3", CommitCategory.BUGFIX, ["db"]),
        _analysis("s4", CommitCategory.BUGFIX, ["db"]),
    ]
    service = PatternDetectionService(
        reader=FakeFileFactReader(),
        analysis_reader=FakeAnalysisReader(analyses),
    )
    report = service.detect("repo-1", bugfix_recurrence_threshold=2)
    assert report.bugfix_recurrences[0].component == "db"
    assert report.bugfix_recurrences[0].bugfix_commit_count == 3
