import pytest

from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
)
from git_it.repository_ingestion.application.ports import CommitSummaryRecord, FileChurnRecord
from git_it.repository_ingestion.domain.patterns import PatternReport


def _record(
    file_path: str = "src/main.py",
    commit_count: int = 3,
    total_insertions: int = 30,
    total_deletions: int = 25,
) -> FileChurnRecord:
    return FileChurnRecord(
        file_path=file_path,
        commit_count=commit_count,
        total_insertions=total_insertions,
        total_deletions=total_deletions,
    )


class FakeFileFactReader:
    def __init__(self, records: list[FileChurnRecord] | None = None) -> None:
        self._records = records or []
        self.calls: list[str] = []

    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        self.calls.append(repository_id)
        return self._records


def test_detect_returns_pattern_report() -> None:
    service = PatternDetectionService(reader=FakeFileFactReader())
    report = service.detect("repo-1")
    assert isinstance(report, PatternReport)
    assert report.repository_id == "repo-1"


def test_detect_identifies_hotspot_above_threshold() -> None:
    reader = FakeFileFactReader(records=[_record(commit_count=10)])
    report = PatternDetectionService(reader=reader).detect("repo-1", hotspot_threshold=5)
    assert len(report.hotspots) == 1
    assert report.hotspots[0].file_path == "src/main.py"


def test_detect_excludes_files_below_threshold() -> None:
    reader = FakeFileFactReader(records=[_record(commit_count=3)])
    report = PatternDetectionService(reader=reader).detect("repo-1", hotspot_threshold=5)
    assert len(report.hotspots) == 0


def test_hotspots_sorted_by_commit_count_descending() -> None:
    records = [
        _record("a.py", commit_count=3),
        _record("b.py", commit_count=10),
        _record("c.py", commit_count=6),
    ]
    report = PatternDetectionService(reader=FakeFileFactReader(records=records)).detect(
        "repo-1", hotspot_threshold=1
    )
    assert [h.commit_count for h in report.hotspots] == [10, 6, 3]


def test_hotspot_churn_equals_insertions_plus_deletions() -> None:
    record = _record(total_insertions=30, total_deletions=25, commit_count=10)
    report = PatternDetectionService(reader=FakeFileFactReader(records=[record])).detect(
        "repo-1", hotspot_threshold=1
    )
    assert report.hotspots[0].churn == 55


def test_detect_passes_repository_id_to_reader() -> None:
    reader = FakeFileFactReader()
    PatternDetectionService(reader=reader).detect("my-repo")
    assert reader.calls == ["my-repo"]


def test_detect_empty_file_facts_returns_no_hotspots() -> None:
    report = PatternDetectionService(reader=FakeFileFactReader()).detect("repo-1")
    assert report.hotspots == []


def test_detect_returns_hotspot_with_correct_file_path_commit_count_and_churn() -> None:
    """Service returns a Hotspot with the expected fields for a known input."""
    records = [
        _record(file_path="src/auth.py", commit_count=8, total_insertions=40, total_deletions=20)
    ]
    reader = FakeFileFactReader(records=records)
    report = PatternDetectionService(reader=reader).detect("repo-1", hotspot_threshold=1)
    assert len(report.hotspots) == 1
    hotspot = report.hotspots[0]
    assert hotspot.file_path == "src/auth.py"
    assert hotspot.commit_count == 8
    assert hotspot.churn == 60


class FakeFileEvidenceReader:
    def __init__(self, evidence: dict[str, tuple[str, ...]] | None = None) -> None:
        self._evidence = evidence or {}

    def get_file_evidence_commits(
        self, repository_id: str, *, limit: int = 5
    ) -> dict[str, tuple[str, ...]]:
        return dict(self._evidence)


class FakeCommitDateReader:
    def __init__(self, date_map: dict[str, str] | None = None) -> None:
        self._date_map = date_map or {}

    def get_commit_date_map(self, repository_id: str) -> dict[str, str]:
        return dict(self._date_map)


def test_detect_passes_evidence_commits_to_hotspot() -> None:
    reader = FakeFileFactReader(records=[_record("src/main.py", commit_count=10)])
    evidence_reader = FakeFileEvidenceReader(evidence={"src/main.py": ("sha1", "sha2", "sha3")})
    service = PatternDetectionService(
        reader=reader,
        file_evidence_reader=evidence_reader,
    )
    report = service.detect("repo-1", hotspot_threshold=1)
    assert len(report.hotspots) == 1
    assert report.hotspots[0].evidence_commit_shas == ("sha1", "sha2", "sha3")


def test_detect_computes_confidence_for_hotspot() -> None:
    reader = FakeFileFactReader(records=[_record("src/main.py", commit_count=10)])
    service = PatternDetectionService(reader=reader)
    report = service.detect("repo-1", hotspot_threshold=1)
    assert report.hotspots[0].confidence == pytest.approx(0.5)


def test_detect_computes_time_range_for_hotspot_from_date_map() -> None:
    reader = FakeFileFactReader(records=[_record("src/main.py", commit_count=10)])
    evidence_reader = FakeFileEvidenceReader(evidence={"src/main.py": ("sha1", "sha2")})
    date_reader = FakeCommitDateReader(date_map={"sha1": "2024-01-01", "sha2": "2024-06-01"})
    service = PatternDetectionService(
        reader=reader,
        file_evidence_reader=evidence_reader,
        commit_date_reader=date_reader,
    )
    report = service.detect("repo-1", hotspot_threshold=1)
    assert report.hotspots[0].time_range == ("2024-01-01", "2024-06-01")


def test_detect_time_range_is_none_when_no_evidence() -> None:
    reader = FakeFileFactReader(records=[_record("src/main.py", commit_count=10)])
    service = PatternDetectionService(reader=reader)
    report = service.detect("repo-1", hotspot_threshold=1)
    assert report.hotspots[0].time_range is None


def test_detect_enrichment_without_readers_returns_defaults() -> None:
    reader = FakeFileFactReader(records=[_record("src/main.py", commit_count=10)])
    service = PatternDetectionService(reader=reader)
    report = service.detect("repo-1", hotspot_threshold=1)
    assert report.hotspots[0].evidence_commit_shas == ()
    assert report.hotspots[0].time_range is None


class FakeCommitSummaryReader:
    def __init__(self, summaries: list[CommitSummaryRecord] | None = None) -> None:
        self._summaries = summaries or []

    def list_commit_messages(self, repository_id: str) -> list[CommitSummaryRecord]:
        return list(self._summaries)


def test_detect_includes_dependency_migrations() -> None:
    reader = FakeFileFactReader()
    summary_reader = FakeCommitSummaryReader(
        summaries=[CommitSummaryRecord(sha="abc1234", message="migrate from requests to httpx")]
    )
    service = PatternDetectionService(reader=reader, commit_summary_reader=summary_reader)
    report = service.detect("repo-1")
    assert len(report.dependency_migrations) == 1
    assert report.dependency_migrations[0].from_dependency == "requests"
    assert report.dependency_migrations[0].to_dependency == "httpx"


def test_detect_includes_architectural_shifts() -> None:
    # Two top-level dirs, src/ with 6 files meets threshold
    records = [_record(f"src/module_{i}/file.py", commit_count=5) for i in range(6)] + [
        _record("tests/test_main.py", commit_count=5),
    ]
    reader = FakeFileFactReader(records=records)
    service = PatternDetectionService(reader=reader)
    report = service.detect("repo-1", hotspot_threshold=100)
    assert len(report.architectural_shifts) >= 1
    shift_types = [s.shift_type for s in report.architectural_shifts]
    assert "new_top_level_dir" in shift_types
