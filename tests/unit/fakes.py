"""Shared test fakes for commit analysis tests.

These fakes are used across multiple test modules.  Import from here instead
of duplicating the class in each file.
"""

from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.domain.github_context import GithubContext


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


class FakeGithubContextReader:
    """Fake GithubContextReader keyed by commit_sha.

    Pass a dict mapping commit_sha → GithubContext | None.
    Any SHA not in the map returns None.
    """

    def __init__(self, context_map: dict[str, GithubContext | None] | None = None) -> None:
        self._context_map: dict[str, GithubContext | None] = context_map or {}
        self.calls: list[dict] = []

    def get_github_context(
        self,
        *,
        repository_id: str,
        canonical_url: str,
        commit_sha: str,
    ) -> GithubContext | None:
        self.calls.append(
            {
                "repository_id": repository_id,
                "canonical_url": canonical_url,
                "commit_sha": commit_sha,
            }
        )
        return self._context_map.get(commit_sha)
