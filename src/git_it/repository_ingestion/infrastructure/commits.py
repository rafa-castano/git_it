from pathlib import Path

import git

from git_it.repository_ingestion.domain.commits import ExtractedCommit, ExtractedFileChange


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
                    message=(commit.message or "").strip(),
                    author_name=commit.author.name or "",
                    committer_name=commit.committer.name or "",
                    parent_shas=tuple(p.hexsha for p in commit.parents),
                    file_changes=self._extract_file_changes(commit),
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
                path=path,
                insertions=int(stat.get("insertions", 0)),
                deletions=int(stat.get("deletions", 0)),
            )
            for path, stat in stats.items()
        )
