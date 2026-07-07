"""Tests for RefreshAllService (spec 028, slice 1).

Mirrors the injection style of ``test_embedding_backfill_service.py``: hand-rolled fakes
for every port, no real git/network/DB. The locked design point under test is that
refresh-all calls only ``RepositoryIngestionService.ingest`` (the free commit-corpus
path) -- never any analysis/narrative/summarizer collaborator, and one repository's
failure (raised exception or a failed ``IngestionResult`` status) never aborts the batch.
"""

import logging
from collections.abc import Callable

import pytest

from git_it.repository_ingestion.application.ports import RepositoryRecord
from git_it.repository_ingestion.application.refresh_all_service import (
    RefreshAllService,
)
from git_it.repository_ingestion.application.service import IngestionResult


def _make_repo(
    *,
    repository_id: str = "repo-1",
    canonical_url: str = "https://github.com/owner/repo",
) -> RepositoryRecord:
    return RepositoryRecord(
        repository_id=repository_id,
        canonical_url=canonical_url,
        status="COMPLETED",
        commit_count=10,
        analysis_count=5,
        has_case_study=True,
    )


def _completed_result(*, canonical_url: str, commits_inserted: int) -> IngestionResult:
    return IngestionResult(
        status="COMPLETED",
        error_code=None,
        stage="COMPLETED",
        retryable=False,
        safe_message=None,
        run_id="run-1",
        canonical_url=canonical_url,
        commits_inserted=commits_inserted,
        commits_reused=0,
        files_inserted=commits_inserted,
        files_reused=0,
    )


def _failed_result(
    *, canonical_url: str, safe_message: str = "Fetch failed safely."
) -> IngestionResult:
    return IngestionResult(
        status="FAILED_FETCH",
        error_code="FETCH_UNREACHABLE",
        stage="FAILED_FETCH",
        retryable=True,
        safe_message=safe_message,
        run_id="run-2",
        canonical_url=canonical_url,
    )


class _FakeRepositoryListReader:
    """Fake RepositoryListReader returning a scripted, fixed repository list."""

    def __init__(self, repositories: list[RepositoryRecord]) -> None:
        self._repositories = repositories

    def list_repositories(self) -> list[RepositoryRecord]:
        return list(self._repositories)


class _SpyIngestPrimitive:
    """Fake per-repo ingest primitive.

    Also exposes an ``analyze_commits`` method that must NEVER be called by
    RefreshAllService -- this is how the no-analysis guarantee is asserted: if the
    service ever reached for an analysis-shaped collaborator, this spy would catch it.
    """

    def __init__(
        self,
        results_by_url: dict[str, IngestionResult] | None = None,
        raise_for_url: dict[str, Exception] | None = None,
    ) -> None:
        self.ingest_calls: list[str] = []
        self.analyze_calls: list[str] = []
        self._results_by_url = results_by_url or {}
        self._raise_for_url = raise_for_url or {}

    def ingest(self, raw_url: str) -> IngestionResult:
        self.ingest_calls.append(raw_url)
        if raw_url in self._raise_for_url:
            raise self._raise_for_url[raw_url]
        return self._results_by_url[raw_url]

    def analyze_commits(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
        self.analyze_calls.append("called")
        raise AssertionError("analysis must never run during refresh-all")


def _factory_for(spy: _SpyIngestPrimitive) -> Callable[[str], _SpyIngestPrimitive]:
    def factory(repository_id: str) -> _SpyIngestPrimitive:
        return spy

    return factory


def test_enumerates_repositories_and_invokes_ingest_once_per_repository() -> None:
    repo_a = _make_repo(repository_id="repo-a", canonical_url="https://github.com/o/a")
    repo_b = _make_repo(repository_id="repo-b", canonical_url="https://github.com/o/b")
    spy = _SpyIngestPrimitive(
        results_by_url={
            "https://github.com/o/a": _completed_result(
                canonical_url="https://github.com/o/a", commits_inserted=3
            ),
            "https://github.com/o/b": _completed_result(
                canonical_url="https://github.com/o/b", commits_inserted=0
            ),
        }
    )
    service = RefreshAllService(
        repository_list_reader=_FakeRepositoryListReader([repo_a, repo_b]),
        ingest_service_factory=_factory_for(spy),
    )

    result = service.refresh_all()

    assert spy.ingest_calls == ["https://github.com/o/a", "https://github.com/o/b"]
    assert result.total_repositories == 2


def test_new_commits_surfaces_ingestion_result_commits_inserted() -> None:
    repo = _make_repo(canonical_url="https://github.com/o/repo")
    spy = _SpyIngestPrimitive(
        results_by_url={
            "https://github.com/o/repo": _completed_result(
                canonical_url="https://github.com/o/repo", commits_inserted=7
            ),
        }
    )
    service = RefreshAllService(
        repository_list_reader=_FakeRepositoryListReader([repo]),
        ingest_service_factory=_factory_for(spy),
    )

    result = service.refresh_all()

    assert len(result.repositories) == 1
    per_repo = result.repositories[0]
    assert per_repo.new_commits == 7
    assert per_repo.status == "completed"
    assert result.total_new_commits == 7
    assert result.refreshed_count == 1
    assert result.failed_count == 0


def test_one_repository_raising_is_isolated_and_others_still_refresh() -> None:
    repo_a = _make_repo(repository_id="repo-a", canonical_url="https://github.com/o/a")
    repo_b = _make_repo(repository_id="repo-b", canonical_url="https://github.com/o/b")
    repo_c = _make_repo(repository_id="repo-c", canonical_url="https://github.com/o/c")
    spy = _SpyIngestPrimitive(
        results_by_url={
            "https://github.com/o/a": _completed_result(
                canonical_url="https://github.com/o/a", commits_inserted=1
            ),
            "https://github.com/o/c": _completed_result(
                canonical_url="https://github.com/o/c", commits_inserted=2
            ),
        },
        raise_for_url={
            "https://github.com/o/b": RuntimeError(
                "connection failed for token=ghp_supersecrettoken123"
            )
        },
    )
    service = RefreshAllService(
        repository_list_reader=_FakeRepositoryListReader([repo_a, repo_b, repo_c]),
        ingest_service_factory=_factory_for(spy),
    )

    result = service.refresh_all()

    assert spy.ingest_calls == [
        "https://github.com/o/a",
        "https://github.com/o/b",
        "https://github.com/o/c",
    ]
    statuses = {r.repository_id: r.status for r in result.repositories}
    assert statuses == {"repo-a": "completed", "repo-b": "failed", "repo-c": "completed"}
    assert result.refreshed_count == 2
    assert result.failed_count == 1

    failed = next(r for r in result.repositories if r.repository_id == "repo-b")
    assert failed.new_commits == 0
    assert failed.safe_message is not None
    assert "ghp_supersecrettoken123" not in (failed.safe_message or "")
    assert "RuntimeError" in (failed.safe_message or "")


def test_one_repository_with_failed_ingestion_status_is_isolated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo_a = _make_repo(repository_id="repo-a", canonical_url="https://github.com/o/a")
    repo_b = _make_repo(repository_id="repo-b", canonical_url="https://github.com/o/b")
    spy = _SpyIngestPrimitive(
        results_by_url={
            "https://github.com/o/a": _completed_result(
                canonical_url="https://github.com/o/a", commits_inserted=4
            ),
            "https://github.com/o/b": _failed_result(
                canonical_url="https://github.com/o/b",
                safe_message="Repository fetch failed safely before analysis could start.",
            ),
        }
    )
    service = RefreshAllService(
        repository_list_reader=_FakeRepositoryListReader([repo_a, repo_b]),
        ingest_service_factory=_factory_for(spy),
    )

    with caplog.at_level(logging.WARNING):
        result = service.refresh_all()

    statuses = {r.repository_id: r.status for r in result.repositories}
    assert statuses == {"repo-a": "completed", "repo-b": "failed"}
    failed = next(r for r in result.repositories if r.repository_id == "repo-b")
    assert failed.error_code == "FETCH_UNREACHABLE"
    assert failed.safe_message == "Repository fetch failed safely before analysis could start."
    assert result.refreshed_count == 1
    assert result.failed_count == 1


def test_no_repositories_reports_nothing_to_refresh_and_makes_no_ingest_calls() -> None:
    spy = _SpyIngestPrimitive()
    service = RefreshAllService(
        repository_list_reader=_FakeRepositoryListReader([]),
        ingest_service_factory=_factory_for(spy),
    )

    result = service.refresh_all()

    assert result.total_repositories == 0
    assert result.repositories == []
    assert result.nothing_to_refresh is True
    assert spy.ingest_calls == []


def test_refresh_all_never_invokes_any_analysis_collaborator() -> None:
    """The free-only lock (spec 028 Goal 3a): refresh-all must never analyze commits.

    The spy's ``analyze_commits`` raises if ever called; asserting it was never touched
    proves RefreshAllService has no path that reaches an analysis-shaped collaborator.
    """
    repo = _make_repo(canonical_url="https://github.com/o/repo")
    spy = _SpyIngestPrimitive(
        results_by_url={
            "https://github.com/o/repo": _completed_result(
                canonical_url="https://github.com/o/repo", commits_inserted=5
            ),
        }
    )
    service = RefreshAllService(
        repository_list_reader=_FakeRepositoryListReader([repo]),
        ingest_service_factory=_factory_for(spy),
    )

    service.refresh_all()

    assert spy.analyze_calls == []
    assert spy.ingest_calls == ["https://github.com/o/repo"]
