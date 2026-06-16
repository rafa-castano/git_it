from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
)
from git_it.repository_ingestion.application.ports import FileChurnRecord, FileOwnershipRecord
from git_it.repository_ingestion.domain.patterns import OwnershipConcentration


class FakeFileFactReader:
    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        return []


class FakeOwnershipReader:
    def __init__(self, records: list[FileOwnershipRecord] | None = None) -> None:
        self._records = records or []
        self.calls: list[str] = []

    def get_file_ownership(self, repository_id: str) -> list[FileOwnershipRecord]:
        self.calls.append(repository_id)
        return list(self._records)


def _record(
    file_path: str = "src/auth.py",
    author_count: int = 1,
    commit_count: int = 5,
) -> FileOwnershipRecord:
    return FileOwnershipRecord(
        file_path=file_path,
        author_count=author_count,
        commit_count=commit_count,
    )


def _service(records: list[FileOwnershipRecord]) -> PatternDetectionService:
    return PatternDetectionService(
        reader=FakeFileFactReader(),
        ownership_reader=FakeOwnershipReader(records),
    )


def test_ownership_concentrations_empty_when_no_reader() -> None:
    service = PatternDetectionService(reader=FakeFileFactReader())
    assert service.detect("repo-1").ownership_concentrations == []


def test_singleton_file_is_detected() -> None:
    report = _service([_record("src/auth.py", author_count=1)]).detect("repo-1")
    assert len(report.ownership_concentrations) == 1
    assert report.ownership_concentrations[0].file_path == "src/auth.py"


def test_file_with_multiple_authors_excluded_by_default() -> None:
    report = _service([_record("src/auth.py", author_count=3)]).detect("repo-1")
    assert report.ownership_concentrations == []


def test_concentration_threshold_is_configurable() -> None:
    records = [
        _record("a.py", author_count=1),
        _record("b.py", author_count=2),
        _record("c.py", author_count=3),
    ]
    report = _service(records).detect("repo-1", ownership_threshold=2)
    paths = {c.file_path for c in report.ownership_concentrations}
    assert paths == {"a.py", "b.py"}


def test_concentrations_sorted_by_commit_count_descending() -> None:
    records = [
        _record("a.py", author_count=1, commit_count=3),
        _record("b.py", author_count=1, commit_count=10),
        _record("c.py", author_count=1, commit_count=7),
    ]
    report = _service(records).detect("repo-1")
    counts = [c.commit_count for c in report.ownership_concentrations]
    assert counts == [10, 7, 3]


def test_ownership_concentration_domain_type() -> None:
    oc = OwnershipConcentration(file_path="src/main.py", author_count=1, commit_count=8)
    assert oc.file_path == "src/main.py"
    assert oc.author_count == 1
    assert oc.commit_count == 8


def test_ownership_reader_receives_repository_id() -> None:
    reader = FakeOwnershipReader([])
    PatternDetectionService(reader=FakeFileFactReader(), ownership_reader=reader).detect("my-repo")
    assert reader.calls == ["my-repo"]
