from pathlib import Path

import git

from git_it.repository_ingestion.domain.commits import ExtractedCommit


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
                )
            )
        return result
