"""Shared test fakes for commit analysis tests.

These fakes are used across multiple test modules.  Import from here instead
of duplicating the class in each file.
"""

from git_it.repository_ingestion.application.commit_query_service import CommitRecord


class FakeCommitReader:
    """Fake implementation of CommitReader that returns a fixed list of records."""

    def __init__(self, records: list[CommitRecord] | None = None) -> None:
        self._records = records or []

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        return self._records[:limit] if limit is not None else list(self._records)
