from dataclasses import dataclass
from pathlib import Path

import pytest

from git_it.cli import main
from git_it.repository_ingestion.application.commit_query_service import CommitRecord


def _make_record(
    sha: str,
    message: str = "Some commit",
    author_name: str = "Alice",
    committed_at: str = "2026-01-15T10:00:00+00:00",
) -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha=sha,
        committed_at=committed_at,
        message=message,
        author_name=author_name,
        committer_name=author_name,
        parent_shas=(),
    )


@dataclass
class CommitQueryCall:
    repository_id: str
    limit: int | None
    order: str
    since: str | None
    until: str | None


class RecordingCommitQueryService:
    def __init__(self, records: list[CommitRecord]) -> None:
        self._records = records
        self.calls: list[CommitQueryCall] = []

    def list_commits(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        self.calls.append(
            CommitQueryCall(
                repository_id=repository_id,
                limit=limit,
                order=order,
                since=since,
                until=until,
            )
        )
        return self._records


def test_commits_cli_prints_recent_commits(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_service = RecordingCommitQueryService(
        [
            _make_record("abc1234abc1234abc1234abc1234abc1234abc1234", "Add feature", "Alice"),
            _make_record("def5678def5678def5678def5678def5678def5678", "Fix bug", "Bob"),
        ]
    )

    def query_factory(*, project_root: Path, repository_id: str) -> RecordingCommitQueryService:
        return query_service

    exit_code = main(
        ["commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_query_factory=query_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "abc1234" in captured.out
    assert "Add feature" in captured.out
    assert "Alice" in captured.out
    assert "def5678" in captured.out
    assert "Fix bug" in captured.out


def test_commits_cli_shows_message_when_no_commits_stored(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_service = RecordingCommitQueryService([])

    def query_factory(*, project_root: Path, repository_id: str) -> RecordingCommitQueryService:
        return query_service

    exit_code = main(
        ["commits", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_query_factory=query_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No commits" in captured.out


def test_commits_cli_passes_limit_to_query_service(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_service = RecordingCommitQueryService([])

    def query_factory(*, project_root: Path, repository_id: str) -> RecordingCommitQueryService:
        return query_service

    main(
        ["commits", "--limit", "5", "https://github.com/owner/repo"],
        project_root=tmp_path,
        commit_query_factory=query_factory,
    )

    assert query_service.calls[0].limit == 5


def test_commits_order_oldest_passed_to_service(tmp_path: Path) -> None:
    query_service = RecordingCommitQueryService([])

    def query_factory(*, project_root: Path, repository_id: str) -> RecordingCommitQueryService:
        return query_service

    main(
        ["commits", "https://github.com/owner/repo", "--order", "oldest"],
        project_root=tmp_path,
        commit_query_factory=query_factory,
    )

    assert query_service.calls[0].order == "oldest"


def test_commits_since_passed_to_service(tmp_path: Path) -> None:
    query_service = RecordingCommitQueryService([])

    def query_factory(*, project_root: Path, repository_id: str) -> RecordingCommitQueryService:
        return query_service

    main(
        ["commits", "https://github.com/owner/repo", "--since", "2024-01-01"],
        project_root=tmp_path,
        commit_query_factory=query_factory,
    )

    assert query_service.calls[0].since == "2024-01-01"
