"""Tests for GitPythonFileTreeReader — spec 029 (slice 1).

Captures the repository's tracked file paths at the default-branch tip from the
local bare clone via ``git ls-tree -r --name-only``, token-independent (no
GitHub API call). Mirrors the bare-repo fixture pattern used by
test_default_branch_reader.py. The reader NEVER raises — every failure mode
(missing/corrupt clone, git error) degrades to an empty list.
"""

from collections.abc import Mapping
from pathlib import Path

import git
import pytest

from git_it.repository_ingestion.infrastructure.commits import GitPythonFileTreeReader


def _make_bare_repo_with_tree(
    tmp_path: Path,
    *,
    files: Mapping[str, str],
    branch_name: str = "main",
) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    source_repo = git.Repo.init(str(source))
    with source_repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test Author")
        cfg.set_value("user", "email", "test@example.com")

    source_repo.git.checkout("-b", branch_name)

    for rel_path, content in files.items():
        target = source / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        source_repo.index.add([rel_path])
    source_repo.index.commit("initial tree")

    bare = tmp_path / "repo.git"
    source_repo.clone(str(bare), bare=True)
    return bare


def test_lists_nested_paths_with_full_relative_path(tmp_path: Path) -> None:
    bare = _make_bare_repo_with_tree(
        tmp_path,
        files={
            "README.md": "# readme",
            "src/git_it/application/ports.py": "x = 1",
            "tests/unit/test_x.py": "y = 2",
        },
    )
    reader = GitPythonFileTreeReader(cache_path=bare)

    paths = reader.read_file_paths()

    assert set(paths) == {
        "README.md",
        "src/git_it/application/ports.py",
        "tests/unit/test_x.py",
    }


def test_uses_explicit_default_branch_when_provided(tmp_path: Path) -> None:
    bare = _make_bare_repo_with_tree(
        tmp_path,
        files={"a.py": "1", "pkg/b.py": "2"},
        branch_name="develop",
    )
    reader = GitPythonFileTreeReader(cache_path=bare, default_branch="develop")

    assert set(reader.read_file_paths()) == {"a.py", "pkg/b.py"}


def test_filters_entries_outside_the_safe_charset(tmp_path: Path) -> None:
    # A filename containing a space is outside [A-Za-z0-9._/-] and must be
    # dropped, while the safe siblings are kept (AC-02). Repo content is
    # untrusted input.
    bare = _make_bare_repo_with_tree(
        tmp_path,
        files={
            "safe.py": "1",
            "src/ok.py": "2",
            "bad name.txt": "3",
        },
    )
    reader = GitPythonFileTreeReader(cache_path=bare)

    paths = reader.read_file_paths()

    assert "bad name.txt" not in paths
    assert set(paths) == {"safe.py", "src/ok.py"}


def test_returns_empty_when_clone_path_does_not_exist(tmp_path: Path) -> None:
    reader = GitPythonFileTreeReader(cache_path=tmp_path / "nonexistent.git")

    assert reader.read_file_paths() == []


def test_returns_empty_for_corrupt_clone(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    (not_a_repo / "file.txt").write_text("not git")

    reader = GitPythonFileTreeReader(cache_path=not_a_repo)

    assert reader.read_file_paths() == []


def test_returns_empty_for_bad_ref(tmp_path: Path) -> None:
    bare = _make_bare_repo_with_tree(tmp_path, files={"a.py": "1"})
    reader = GitPythonFileTreeReader(cache_path=bare, default_branch="no-such-branch")

    assert reader.read_file_paths() == []


@pytest.mark.parametrize("empty_dir_name", ["empty.git"])
def test_returns_empty_for_repo_without_commits(tmp_path: Path, empty_dir_name: str) -> None:
    # An initialized-but-empty repo has no HEAD tree; ls-tree fails → [].
    empty = tmp_path / empty_dir_name
    git.Repo.init(str(empty), bare=True)
    reader = GitPythonFileTreeReader(cache_path=empty)

    assert reader.read_file_paths() == []
