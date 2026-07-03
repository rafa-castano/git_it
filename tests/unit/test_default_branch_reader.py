"""Tests for GitPythonDefaultBranchReader — spec 020.

Captures the repository's default branch from the local bare clone's HEAD
symbolic reference, token-independent (no GitHub API call). Mirrors the
bare-repo fixture pattern used by test_git_commit_extractor.py.
"""

from pathlib import Path

import git
import pytest

from git_it.repository_ingestion.infrastructure.commits import GitPythonDefaultBranchReader


def _make_bare_repo(tmp_path: Path, *, branch_name: str = "main") -> Path:
    source = tmp_path / "source"
    source.mkdir()
    source_repo = git.Repo.init(str(source))
    with source_repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test Author")
        cfg.set_value("user", "email", "test@example.com")

    # Explicitly name the branch so the test does not depend on the ambient
    # git config's init.defaultBranch.
    source_repo.git.checkout("-b", branch_name)

    (source / "a.txt").write_text("first")
    source_repo.index.add(["a.txt"])
    source_repo.index.commit("first commit")

    bare = tmp_path / "repo.git"
    source_repo.clone(str(bare), bare=True)
    return bare


@pytest.fixture()
def bare_repo_main(tmp_path: Path) -> Path:
    return _make_bare_repo(tmp_path, branch_name="main")


def test_reads_default_branch_from_bare_clone_head(bare_repo_main: Path) -> None:
    reader = GitPythonDefaultBranchReader(cache_path=bare_repo_main)

    assert reader.read_default_branch() == "main"


def test_reads_a_non_main_branch_name(tmp_path: Path) -> None:
    bare = _make_bare_repo(tmp_path, branch_name="develop")
    reader = GitPythonDefaultBranchReader(cache_path=bare)

    assert reader.read_default_branch() == "develop"


def test_returns_none_for_detached_head(bare_repo_main: Path) -> None:
    # Simulate a detached HEAD by rewriting the bare clone's HEAD file to a
    # raw commit SHA instead of a symbolic ref.
    repo = git.Repo(str(bare_repo_main))
    sha = repo.head.commit.hexsha
    (bare_repo_main / "HEAD").write_text(sha + "\n")

    reader = GitPythonDefaultBranchReader(cache_path=bare_repo_main)

    assert reader.read_default_branch() is None


def test_returns_none_for_unsafe_branch_name(bare_repo_main: Path) -> None:
    # Directly rewrite HEAD to point at a ref name that git's own porcelain
    # would never let you create, to exercise the reader's own defense-in-depth
    # charset validation (CODEX.md: treat repository content as untrusted).
    (bare_repo_main / "HEAD").write_text("ref: refs/heads/weird;rm -rf\n")

    reader = GitPythonDefaultBranchReader(cache_path=bare_repo_main)

    assert reader.read_default_branch() is None


def test_returns_none_for_branch_name_with_dot_dot(bare_repo_main: Path) -> None:
    (bare_repo_main / "HEAD").write_text("ref: refs/heads/../etc\n")

    reader = GitPythonDefaultBranchReader(cache_path=bare_repo_main)

    assert reader.read_default_branch() is None


def test_returns_none_when_clone_path_does_not_exist(tmp_path: Path) -> None:
    reader = GitPythonDefaultBranchReader(cache_path=tmp_path / "nonexistent.git")

    assert reader.read_default_branch() is None
