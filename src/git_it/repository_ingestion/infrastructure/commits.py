import re
from pathlib import Path

import git

from git_it.repository_ingestion.domain.commits import ExtractedCommit, ExtractedFileChange

_SAFE_BRANCH_NAME = re.compile(r"^[A-Za-z0-9._/-]+$")


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

    def extract_commits(self) -> list[ExtractedCommit]:
        repo = git.Repo(str(self._cache_path))
        result = []
        for commit in repo.iter_commits():
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
