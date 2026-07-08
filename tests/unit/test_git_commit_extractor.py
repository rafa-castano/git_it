import datetime
from pathlib import Path
from types import SimpleNamespace

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


def test_git_commit_extractor_populates_file_changes_per_commit(
    bare_fixture_repo: Path,
) -> None:
    extractor = GitPythonCommitExtractor(cache_path=bare_fixture_repo)

    commits = extractor.extract_commits()

    # every commit in the fixture adds exactly one file
    for commit in commits:
        assert len(commit.file_changes) == 1
        assert commit.file_changes[0].path.endswith(".txt")
        assert commit.file_changes[0].insertions >= 0
        assert commit.file_changes[0].deletions >= 0


# ---------------------------------------------------------------------------
# Spec 030 — incremental extraction: skip already-stored commits without
# computing their per-commit ``git diff`` (commit.stats).
# ---------------------------------------------------------------------------


class _SpyStats:
    def __init__(self) -> None:
        self.files = {"file.py": {"insertions": 1, "deletions": 0}}


class _SpyCommit:
    """Fake GitPython commit that records every ``.stats`` access.

    ``.stats`` is the expensive per-commit ``git diff`` the extractor must skip
    for commits already stored (spec 030 AC-02/AC-08).
    """

    def __init__(self, sha: str, accessed: list[str]) -> None:
        self.hexsha = sha
        self._accessed = accessed

    @property
    def committed_datetime(self) -> datetime.datetime:
        return datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

    @property
    def message(self) -> str:
        return f"message {self.hexsha}"

    @property
    def author(self) -> SimpleNamespace:
        return SimpleNamespace(name="Author", email="author@example.com")

    @property
    def committer(self) -> SimpleNamespace:
        return SimpleNamespace(name="Committer", email="committer@example.com")

    @property
    def parents(self) -> tuple[()]:
        return ()

    @property
    def stats(self) -> _SpyStats:
        self._accessed.append(self.hexsha)
        return _SpyStats()


class _SpyRepo:
    def __init__(self, commits: list[_SpyCommit]) -> None:
        self._commits = commits

    def iter_commits(self) -> object:
        return iter(self._commits)


def test_git_commit_extractor_skips_stats_and_emits_only_new_commits_for_skip_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    accessed: list[str] = []
    commits = [_SpyCommit("new-sha", accessed), _SpyCommit("stored-sha", accessed)]
    monkeypatch.setattr(
        "git_it.repository_ingestion.infrastructure.commits.git.Repo",
        lambda _path: _SpyRepo(commits),
    )
    extractor = GitPythonCommitExtractor(cache_path=tmp_path)

    result = extractor.extract_commits(frozenset({"stored-sha"}))

    # Only the new commit is emitted (AC-03); the stored one is dropped (AC-02).
    assert [c.sha for c in result] == ["new-sha"]
    # commit.stats was accessed ONLY for the new commit, never for the skipped one.
    assert accessed == ["new-sha"]


def test_git_commit_extractor_accesses_no_stats_when_all_commits_are_skipped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    accessed: list[str] = []
    commits = [_SpyCommit("a", accessed), _SpyCommit("b", accessed)]
    monkeypatch.setattr(
        "git_it.repository_ingestion.infrastructure.commits.git.Repo",
        lambda _path: _SpyRepo(commits),
    )
    extractor = GitPythonCommitExtractor(cache_path=tmp_path)

    result = extractor.extract_commits(frozenset({"a", "b"}))

    # AC-08: zero per-commit git diffs when nothing is new.
    assert result == []
    assert accessed == []


def test_git_commit_extractor_full_extraction_when_skip_set_empty(
    bare_fixture_repo: Path,
) -> None:
    extractor = GitPythonCommitExtractor(cache_path=bare_fixture_repo)

    # AC-05: empty skip-set behaves exactly like the no-arg call (full extraction).
    assert len(extractor.extract_commits()) == 3
    assert len(extractor.extract_commits(frozenset())) == 3
