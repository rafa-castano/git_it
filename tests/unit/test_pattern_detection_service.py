from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
)
from git_it.repository_ingestion.application.ports import FileChurnRecord
from git_it.repository_ingestion.domain.patterns import Hotspot, PatternReport


def _record(
    file_path: str = "src/main.py",
    commit_count: int = 3,
    total_insertions: int = 10,
    total_deletions: int = 5,
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
    record = _record(total_insertions=30, total_deletions=15, commit_count=10)
    report = PatternDetectionService(reader=FakeFileFactReader(records=[record])).detect(
        "repo-1", hotspot_threshold=1
    )
    assert report.hotspots[0].churn == 45


def test_detect_passes_repository_id_to_reader() -> None:
    reader = FakeFileFactReader()
    PatternDetectionService(reader=reader).detect("my-repo")
    assert reader.calls == ["my-repo"]


def test_detect_empty_file_facts_returns_no_hotspots() -> None:
    report = PatternDetectionService(reader=FakeFileFactReader()).detect("repo-1")
    assert report.hotspots == []


def test_hotspot_is_a_dataclass_with_expected_fields() -> None:
    h = Hotspot(file_path="x.py", commit_count=7, total_insertions=20, total_deletions=10)
    assert h.file_path == "x.py"
    assert h.commit_count == 7
    assert h.churn == 30
