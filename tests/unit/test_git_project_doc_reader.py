"""Tests for GitPythonProjectDocReader — spec 025.

Captures a repository's root-level README/CHANGELOG from the local bare
clone's HEAD tree, token-independent (no GitHub API call). Mirrors the
bare-repo fixture pattern used by test_default_branch_reader.py.
"""

from pathlib import Path

import git
import pytest

from git_it.repository_ingestion.infrastructure.project_docs import (
    PROJECT_DOC_MAX_CHARS,
    GitPythonProjectDocReader,
)


def _make_bare_repo(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    source_repo = git.Repo.init(str(source))
    with source_repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test Author")
        cfg.set_value("user", "email", "test@example.com")

    source_repo.git.checkout("-b", "main")

    added = []
    for name, content in files.items():
        path = source / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            # newline="" avoids Windows' write_text() translating "\n" to
            # "\r\n", which would make the committed blob content diverge
            # from the exact string under test.
            path.write_text(content, newline="")
        added.append(name)
    source_repo.index.add(added)
    source_repo.index.commit("add project docs")

    bare = tmp_path / "repo.git"
    source_repo.clone(str(bare), bare=True)
    return bare


def test_reads_readme_from_bare_clone(tmp_path: Path) -> None:
    bare = _make_bare_repo(tmp_path, {"README.md": "# My Project\n\nDoes X."})
    reader = GitPythonProjectDocReader(cache_path=bare)

    content = reader.read_project_docs("repo-1")

    assert content is not None
    assert content.repository_id == "repo-1"
    assert content.readme_text == "# My Project\n\nDoes X."
    assert content.readme_truncated is False
    assert content.changelog_text is None
    assert content.changelog_truncated is False


def test_reads_changelog_independently_of_readme(tmp_path: Path) -> None:
    bare = _make_bare_repo(tmp_path, {"CHANGELOG.md": "## 1.0.0\n\n- Initial release"})
    reader = GitPythonProjectDocReader(cache_path=bare)

    content = reader.read_project_docs("repo-2")

    assert content is not None
    assert content.readme_text is None
    assert content.changelog_text == "## 1.0.0\n\n- Initial release"
    assert content.changelog_truncated is False


def test_reads_both_readme_and_changelog_in_same_content(tmp_path: Path) -> None:
    bare = _make_bare_repo(
        tmp_path,
        {
            "README.md": "# My Project",
            "CHANGELOG.md": "## 1.0.0",
        },
    )
    reader = GitPythonProjectDocReader(cache_path=bare)

    content = reader.read_project_docs("repo-3")

    assert content is not None
    assert content.readme_text == "# My Project"
    assert content.changelog_text == "## 1.0.0"


@pytest.mark.parametrize("readme_name", ["Readme.md", "README.rst", "readme.markdown"])
def test_case_insensitive_and_extension_variants_for_readme(
    tmp_path: Path, readme_name: str
) -> None:
    bare = _make_bare_repo(tmp_path, {readme_name: "content"})
    reader = GitPythonProjectDocReader(cache_path=bare)

    content = reader.read_project_docs("repo-4")

    assert content is not None
    assert content.readme_text == "content"


def test_returns_none_when_neither_file_present(tmp_path: Path) -> None:
    bare = _make_bare_repo(tmp_path, {"a.txt": "unrelated file"})
    reader = GitPythonProjectDocReader(cache_path=bare)

    assert reader.read_project_docs("repo-5") is None


def test_oversized_readme_is_truncated_with_flag_set(tmp_path: Path) -> None:
    oversized = "x" * (PROJECT_DOC_MAX_CHARS + 500)
    bare = _make_bare_repo(tmp_path, {"README.md": oversized})
    reader = GitPythonProjectDocReader(cache_path=bare)

    content = reader.read_project_docs("repo-6")

    assert content is not None
    assert content.readme_text == oversized[:PROJECT_DOC_MAX_CHARS]
    assert content.readme_truncated is True


def test_under_budget_readme_is_not_marked_truncated(tmp_path: Path) -> None:
    under_budget = "y" * (PROJECT_DOC_MAX_CHARS - 10)
    bare = _make_bare_repo(tmp_path, {"README.md": under_budget})
    reader = GitPythonProjectDocReader(cache_path=bare)

    content = reader.read_project_docs("repo-7")

    assert content is not None
    assert content.readme_text == under_budget
    assert content.readme_truncated is False


def test_non_utf8_readme_is_skipped_not_raised(tmp_path: Path) -> None:
    bare = _make_bare_repo(
        tmp_path,
        {
            "README.md": b"\xff\xfe invalid",
            "CHANGELOG.md": "## 1.0.0",
        },
    )
    reader = GitPythonProjectDocReader(cache_path=bare)

    content = reader.read_project_docs("repo-8")

    assert content is not None
    assert content.readme_text is None
    assert content.changelog_text == "## 1.0.0"


def test_returns_none_when_clone_path_does_not_exist(tmp_path: Path) -> None:
    reader = GitPythonProjectDocReader(cache_path=tmp_path / "nonexistent.git")

    assert reader.read_project_docs("repo-9") is None
