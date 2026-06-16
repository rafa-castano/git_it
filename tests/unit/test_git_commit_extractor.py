from pathlib import Path

import git
import pytest

from git_it.repository_ingestion.infrastructure.commits import GitPythonCommitExtractor


@pytest.fixture()
def bare_fixture_repo(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    source_repo = git.Repo.init(str(source))
    with source_repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test Author")
        cfg.set_value("user", "email", "test@example.com")

    (source / "a.txt").write_text("first")
    source_repo.index.add(["a.txt"])
    source_repo.index.commit("first commit")

    (source / "b.txt").write_text("second")
    source_repo.index.add(["b.txt"])
    source_repo.index.commit("second commit")

    (source / "c.txt").write_text("third")
    source_repo.index.add(["c.txt"])
    source_repo.index.commit("third commit")

    bare = tmp_path / "repo.git"
    source_repo.clone(str(bare), bare=True)
    return bare


def test_git_commit_extractor_returns_all_commits_from_bare_repo(
    bare_fixture_repo: Path,
) -> None:
    extractor = GitPythonCommitExtractor(cache_path=bare_fixture_repo)

    commits = extractor.extract_commits()

    assert len(commits) == 3


def test_git_commit_extractor_returns_commits_in_reverse_chronological_order(
    bare_fixture_repo: Path,
) -> None:
    extractor = GitPythonCommitExtractor(cache_path=bare_fixture_repo)

    commits = extractor.extract_commits()

    assert commits[0].message == "third commit"
    assert commits[1].message == "second commit"
    assert commits[2].message == "first commit"


def test_git_commit_extractor_populates_required_fields(
    bare_fixture_repo: Path,
) -> None:
    extractor = GitPythonCommitExtractor(cache_path=bare_fixture_repo)

    commits = extractor.extract_commits()
    latest = commits[0]

    assert len(latest.sha) == 40
    assert latest.committed_at
    assert latest.message == "third commit"
    assert latest.author_name == "Test Author"
    assert latest.committer_name == "Test Author"


def test_git_commit_extractor_records_parent_shas(
    bare_fixture_repo: Path,
) -> None:
    extractor = GitPythonCommitExtractor(cache_path=bare_fixture_repo)

    commits = extractor.extract_commits()

    assert len(commits[0].parent_shas) == 1
    assert commits[0].parent_shas[0] == commits[1].sha
    assert len(commits[2].parent_shas) == 0
