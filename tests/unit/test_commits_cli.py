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


class RecordingCommitQueryService:
    def __init__(self, records: list[CommitRecord]) -> None:
        self._records = records
        self.calls: list[tuple[str, int | None]] = []

    def list_commits(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
    ) -> list[CommitRecord]:
        self.calls.append((repository_id, limit))
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

    assert query_service.calls[0][1] == 5
