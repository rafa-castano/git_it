from pathlib import Path

import pytest

from git_it.repository_ingestion.application.refresh_all_service import (
    RefreshAllResult,
    RepositoryRefreshResult,
)
from git_it.repository_ingestion.interfaces.cli import main


class FakeRefreshAllService:
    def __init__(self, result: RefreshAllResult) -> None:
        self._result = result
        self.refresh_all_calls = 0

    def refresh_all(self) -> RefreshAllResult:
        self.refresh_all_calls += 1
        return self._result


def _factory(service: FakeRefreshAllService):  # type: ignore[no-untyped-def]
    def factory(*, project_root: Path) -> FakeRefreshAllService:
        return service

    return factory


_EMPTY_RESULT = RefreshAllResult(
    repositories=[],
    total_repositories=0,
    refreshed_count=0,
    failed_count=0,
    total_new_commits=0,
)


def test_refresh_all_empty_prints_nothing_to_refresh_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeRefreshAllService(_EMPTY_RESULT)

    code = main(
        ["refresh-all"],
        project_root=tmp_path,
        refresh_all_factory=_factory(service),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "no repositories to refresh" in captured.out.lower()
    assert service.refresh_all_calls == 1


def test_refresh_all_reports_per_repository_new_commits_and_totals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = RefreshAllResult(
        repositories=[
            RepositoryRefreshResult(
                repository_id="repo-a",
                canonical_url="https://github.com/owner/repo-a",
                status="completed",
                new_commits=3,
            ),
            RepositoryRefreshResult(
                repository_id="repo-b",
                canonical_url="https://github.com/owner/repo-b",
                status="completed",
                new_commits=0,
            ),
        ],
        total_repositories=2,
        refreshed_count=2,
        failed_count=0,
        total_new_commits=3,
    )
    service = FakeRefreshAllService(result)

    code = main(
        ["refresh-all"],
        project_root=tmp_path,
        refresh_all_factory=_factory(service),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "owner/repo-a" in captured.out
    assert "3 new commit" in captured.out
    assert "owner/repo-b" in captured.out
    assert "0 new commit" in captured.out
    assert "2 repositories" in captured.out
    assert "3 new commits" in captured.out


def test_refresh_all_reports_failed_repository_without_aborting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = RefreshAllResult(
        repositories=[
            RepositoryRefreshResult(
                repository_id="repo-a",
                canonical_url="https://github.com/owner/repo-a",
                status="completed",
                new_commits=2,
            ),
            RepositoryRefreshResult(
                repository_id="repo-b",
                canonical_url="https://github.com/owner/repo-b",
                status="failed",
                new_commits=0,
                error_code="FAILED_FETCH",
                safe_message="Refresh failed: ConnectionError",
            ),
        ],
        total_repositories=2,
        refreshed_count=1,
        failed_count=1,
        total_new_commits=2,
    )
    service = FakeRefreshAllService(result)

    code = main(
        ["refresh-all"],
        project_root=tmp_path,
        refresh_all_factory=_factory(service),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "owner/repo-a" in captured.out
    assert "owner/repo-b" in captured.out
    assert "Refresh failed: ConnectionError" in captured.out
    assert "1 failed" in captured.out


def test_refresh_all_returns_zero_on_normal_run(tmp_path: Path) -> None:
    service = FakeRefreshAllService(_EMPTY_RESULT)

    code = main(
        ["refresh-all"],
        project_root=tmp_path,
        refresh_all_factory=_factory(service),
    )

    assert code == 0
