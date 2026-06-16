from git_it.repository_ingestion.application.pattern_detection_service import (
    PatternDetectionService,
)
from git_it.repository_ingestion.application.ports import CommitSummaryRecord, FileChurnRecord


class FakeFileFactReader:
    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        return []


class FakeCommitSummaryReader:
    def __init__(self, messages: list[str] | None = None) -> None:
        self._messages = messages or []
        self.calls: list[str] = []

    def list_commit_messages(self, repository_id: str) -> list[CommitSummaryRecord]:
        self.calls.append(repository_id)
        return [CommitSummaryRecord(sha=f"sha{i}", message=m) for i, m in enumerate(self._messages)]


def _service(messages: list[str]) -> PatternDetectionService:
    return PatternDetectionService(
        reader=FakeFileFactReader(),
        commit_summary_reader=FakeCommitSummaryReader(messages),
    )


def test_no_revert_signal_when_no_reader() -> None:
    service = PatternDetectionService(reader=FakeFileFactReader())
    assert service.detect("repo-1").revert_signal is None


def test_no_revert_signal_when_no_revert_commits() -> None:
    report = _service(["feat: add login", "fix: null pointer", "docs: readme"]).detect("repo-1")
    assert report.revert_signal is None


def test_revert_prefix_is_detected() -> None:
    report = _service(['Revert "feat: add login"', "fix: something"]).detect("repo-1")
    assert report.revert_signal is not None
    assert report.revert_signal.revert_count == 1


def test_multiple_reverts_counted() -> None:
    messages = [
        'Revert "feat: add login"',
        'Revert "fix: null pointer"',
        "feat: new feature",
    ]
    report = _service(messages).detect("repo-1")
    assert report.revert_signal is not None
    assert report.revert_signal.revert_count == 2


def test_revert_ratio_is_correct() -> None:
    messages = ['Revert "feat: login"', "feat: other", "fix: bug", "chore: cleanup"]
    report = _service(messages).detect("repo-1")
    assert report.revert_signal is not None
    assert report.revert_signal.revert_ratio == 0.25


def test_revert_threshold_suppresses_signal() -> None:
    report = _service(['Revert "feat: login"']).detect("repo-1", revert_threshold=2)
    assert report.revert_signal is None


def test_revert_detection_case_insensitive_prefix() -> None:
    report = _service(["revert: undo commit abc"]).detect("repo-1")
    assert report.revert_signal is not None
    assert report.revert_signal.revert_count == 1


def test_commit_summary_reader_receives_repository_id() -> None:
    reader = FakeCommitSummaryReader([])
    PatternDetectionService(reader=FakeFileFactReader(), commit_summary_reader=reader).detect(
        "my-repo"
    )
    assert reader.calls == ["my-repo"]
