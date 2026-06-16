from git_it.repository_ingestion.application.commit_query_service import (
    CommitRecord,
    RepositoryCommitQueryService,
)


def _make_record(sha: str, committed_at: str = "2026-01-01") -> CommitRecord:
    return CommitRecord(
        repository_id="repo-1",
        sha=sha,
        committed_at=committed_at,
        message="commit",
        author_name="Author",
        committer_name="Author",
        parent_shas=(),
    )


class FakeCommitReader:
    def __init__(self, records: list[CommitRecord]) -> None:
        self._records = records
        self.calls: list[tuple[str, int | None]] = []

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
    ) -> list[CommitRecord]:
        self.calls.append((repository_id, limit))
        return self._records


def test_list_commits_delegates_to_reader() -> None:
    records = [_make_record("aaa"), _make_record("bbb")]
    reader = FakeCommitReader(records)
    service = RepositoryCommitQueryService(reader=reader)

    result = service.list_commits("repo-1")

    assert result == records
    assert reader.calls == [("repo-1", None)]


def test_list_commits_passes_limit_to_reader() -> None:
    reader = FakeCommitReader([])
    service = RepositoryCommitQueryService(reader=reader)

    service.list_commits("repo-1", limit=5)

    assert reader.calls == [("repo-1", 5)]


def test_list_commits_returns_empty_list_when_reader_has_none() -> None:
    reader = FakeCommitReader([])
    service = RepositoryCommitQueryService(reader=reader)

    result = service.list_commits("repo-1")

    assert result == []
