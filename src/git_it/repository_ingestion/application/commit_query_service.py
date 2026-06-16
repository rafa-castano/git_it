from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommitRecord:
    repository_id: str
    sha: str
    committed_at: str
    message: str
    author_name: str
    committer_name: str
    parent_shas: tuple[str, ...]


class CommitReader(Protocol):
    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]: ...


class RepositoryCommitQueryService:
    def __init__(self, *, reader: CommitReader) -> None:
        self._reader = reader

    def list_commits(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        return self._reader.list_commits_for_repository(
            repository_id, limit=limit, order=order, since=since, until=until
        )
