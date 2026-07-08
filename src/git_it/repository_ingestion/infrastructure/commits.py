import re
from pathlib import Path

import git

from git_it.repository_ingestion.domain.commits import ExtractedCommit, ExtractedFileChange

_SAFE_BRANCH_NAME = re.compile(r"^[A-Za-z0-9._/-]+$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")


def _is_safe_path(path: str) -> bool:
    """Defense-in-depth charset gate for a file path read from local git data.

    Mirrors ``_is_safe_branch_name``: a path from ``git ls-tree`` is repository
    content and therefore untrusted input (CODEX.md). Keep it only if it matches
    the fixed safe charset, contains no ``..``, and does not start with ``/``
    (spec 029 AC-02) — so it can never be smuggled into a GitHub URL path.
    """
    if not path:
        return False
    if ".." in path or path.startswith("/"):
        return False
    return bool(_SAFE_PATH.fullmatch(path))


def _is_safe_branch_name(name: str) -> bool:
    """Defense-in-depth charset check for a branch name read from local git data.

    Git's own porcelain refuses to create refs with unsafe characters, but
    HEAD's target is read here as raw ref-file text (see
    GitPythonDefaultBranchReader), so it is treated as untrusted input
    (CODEX.md) before it is ever persisted or used to build a GitHub URL.
    """
    if not name:
        return False
    if ".." in name or name.startswith("/") or name.endswith("/"):
        return False
    return bool(_SAFE_BRANCH_NAME.fullmatch(name))


class GitPythonCommitExtractor:
    def __init__(self, *, cache_path: Path) -> None:
        self._cache_path = cache_path

    def extract_commits(self, skip_shas: frozenset[str] = frozenset()) -> list[ExtractedCommit]:
        repo = git.Repo(str(self._cache_path))
        result = []
        for commit in repo.iter_commits():
            # Spec 030: for a commit already stored, skip both the ExtractedCommit
            # build AND the expensive per-commit ``git diff`` (commit.stats) that
            # ``_extract_file_changes`` triggers. ``commit.hexsha`` is cheap metadata.
            if commit.hexsha in skip_shas:
                continue
            result.append(
                ExtractedCommit(
                    sha=commit.hexsha,
                    committed_at=commit.committed_datetime.isoformat(),
                    message=str(commit.message or "").strip(),
                    author_name=commit.author.name or "",
                    committer_name=commit.committer.name or "",
                    parent_shas=tuple(p.hexsha for p in commit.parents),
                    file_changes=self._extract_file_changes(commit),
                    author_email=commit.author.email or "",
                )
            )
        return result

    @staticmethod
    def _extract_file_changes(commit: git.Commit) -> tuple[ExtractedFileChange, ...]:
        try:
            stats = commit.stats.files
        except Exception:
            return ()
        return tuple(
            ExtractedFileChange(
                path=str(path),
                insertions=int(stat.get("insertions", 0)),
                deletions=int(stat.get("deletions", 0)),
            )
            for path, stat in stats.items()
        )


class GitPythonDefaultBranchReader:
    """Reads a repository's default branch from the local bare clone's HEAD.

    Token-independent (no GitHub API call): after ``git clone``, the bare
    clone's HEAD symbolic reference already points at whatever branch was the
    remote's default at clone time (spec 020). Never raises — every failure
    mode (detached HEAD, unresolvable ref, unsafe ref name, missing/corrupt
    clone) degrades to ``None``, matching the "no branch -> no linking"
    acceptable degradation documented in the spec.
    """

    def __init__(self, *, cache_path: Path) -> None:
        self._cache_path = cache_path

    def read_default_branch(self) -> str | None:
        try:
            repo = git.Repo(str(self._cache_path))
            if repo.head.is_detached:
                return None
            name = repo.head.reference.name
        except Exception:
            return None
        return name if _is_safe_branch_name(name) else None


class GitPythonFileTreeReader:
    """Lists a repository's tracked file paths from the local bare clone (spec 029).

    Token-independent (no GitHub API call): runs ``git ls-tree -r --name-only``
    against the same bare clone ``GitPythonCommitExtractor`` /
    ``GitPythonDefaultBranchReader`` open, at ``default_branch`` when provided
    else ``HEAD`` (which, for a bare clone, already points at the default-branch
    tip). Every returned path passes the safe-charset gate; every failure mode
    (missing/corrupt clone, unknown ref, empty repo) degrades to ``[]`` — the
    reader never raises.
    """

    def __init__(self, *, cache_path: Path, default_branch: str | None = None) -> None:
        self._cache_path = cache_path
        self._default_branch = default_branch

    def read_file_paths(self) -> list[str]:
        try:
            repo = git.Repo(str(self._cache_path))
            ref = self._default_branch or "HEAD"
            output = repo.git.ls_tree("-r", "--name-only", ref)
        except Exception:
            return []
        return [line for line in output.splitlines() if _is_safe_path(line)]
