from pathlib import Path

import pytest

from git_it.repository_ingestion.application.ports import CaseStudyRecord
from git_it.repository_ingestion.infrastructure.sqlite import SqliteCaseStudyStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    SqliteCaseStudyStore(path).initialize()
    return path


def test_get_case_study_returns_none_when_empty(db_path: Path) -> None:
    assert SqliteCaseStudyStore(db_path).get_case_study("repo-1") is None


def test_save_and_get_case_study(db_path: Path) -> None:
    record = CaseStudyRecord(
        repository_id="repo-1",
        narrative="# Case Study\nContent here.",
        commit_count=10,
        hotspot_count=3,
    )
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(record)
    result = store.get_case_study("repo-1")
    assert result is not None
    assert result.repository_id == "repo-1"
    assert result.narrative == "# Case Study\nContent here."
    assert result.commit_count == 10
    assert result.hotspot_count == 3


def test_save_overwrites_existing(db_path: Path) -> None:
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(repository_id="repo-1", narrative="old", commit_count=5, hotspot_count=1)
    )
    store.save_case_study(
        CaseStudyRecord(repository_id="repo-1", narrative="new", commit_count=7, hotspot_count=2)
    )
    result = store.get_case_study("repo-1")
    assert result is not None
    assert result.narrative == "new"
    assert result.commit_count == 7


def test_get_case_study_isolated_by_repository(db_path: Path) -> None:
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1", narrative="repo1 study", commit_count=5, hotspot_count=0
        )
    )
    assert store.get_case_study("repo-2") is None


def test_get_repo_context_returns_none_when_no_case_study(db_path: Path) -> None:
    assert SqliteCaseStudyStore(db_path).get_repo_context("repo-1") is None


def test_get_repo_context_truncates_long_narrative(db_path: Path) -> None:
    long_narrative = "x" * 5000
    store = SqliteCaseStudyStore(db_path)
    store.save_case_study(
        CaseStudyRecord(
            repository_id="repo-1",
            narrative=long_narrative,
            commit_count=1,
            hotspot_count=0,
        )
    )
    result = store.get_repo_context("repo-1")
    assert result is not None
    assert len(result) <= 2000
