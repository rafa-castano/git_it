"""GitPython-based reader for root-level README/CHANGELOG content (spec 025).

Lives in its own module rather than alongside ``GitPythonDefaultBranchReader``
in ``infrastructure/commits.py``: this reader does meaningfully more work
(tree traversal, case-insensitive name matching, decoding, truncation) than a
one-line HEAD-ref read, and ``commits.py`` is already a sizable file covering
commit extraction and default-branch capture.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

import git

from git_it.repository_ingestion.domain.project_docs import ProjectDocContent

PROJECT_DOC_MAX_CHARS = int(os.environ.get("PROJECT_DOC_MAX_CHARS", "2000"))

_README_NAMES = ("readme.md", "readme.rst", "readme.markdown", "readme.txt", "readme")
_CHANGELOG_NAMES = (
    "changelog.md",
    "changelog.rst",
    "changelog.markdown",
    "changelog.txt",
    "changelog",
)


def _read_blob_text(tree: git.Tree, candidate_names: tuple[str, ...]) -> str | None:
    """Case-insensitively match a root-level blob against candidate names.

    Returns the decoded UTF-8 text, or ``None`` if no candidate matches or the
    matching blob's content cannot be decoded as UTF-8 (that file is then
    treated as absent — never raised, matching this reader's "never raise"
    contract).
    """
    for blob in tree.blobs:
        if blob.name.lower() not in candidate_names:
            continue
        try:
            raw_bytes: bytes = blob.data_stream.read()
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) > PROJECT_DOC_MAX_CHARS:
        return text[:PROJECT_DOC_MAX_CHARS], True
    return text, False


class GitPythonProjectDocReader:
    """Reads a repository's root-level README/CHANGELOG from its local bare clone.

    Token-independent (no GitHub API call): reads only from the local git
    clone already required for commit mining (spec 025). Never raises — every
    failure mode (missing/corrupt clone, detached HEAD, decode failure) simply
    treats that file (or the whole read) as absent, mirroring
    ``GitPythonDefaultBranchReader``'s "never raises" contract exactly.
    """

    def __init__(self, *, cache_path: Path) -> None:
        self._cache_path = cache_path

    def get_project_docs(self, repository_id: str) -> ProjectDocContent | None:
        try:
            repo = git.Repo(str(self._cache_path))
            tree = repo.head.commit.tree
        except Exception:
            return None

        readme_raw = _read_blob_text(tree, _README_NAMES)
        changelog_raw = _read_blob_text(tree, _CHANGELOG_NAMES)

        if readme_raw is None and changelog_raw is None:
            return None

        readme_text: str | None = None
        readme_truncated = False
        if readme_raw is not None:
            readme_text, readme_truncated = _truncate(readme_raw)

        changelog_text: str | None = None
        changelog_truncated = False
        if changelog_raw is not None:
            changelog_text, changelog_truncated = _truncate(changelog_raw)

        return ProjectDocContent(
            repository_id=repository_id,
            readme_text=readme_text,
            readme_truncated=readme_truncated,
            changelog_text=changelog_text,
            changelog_truncated=changelog_truncated,
            captured_at=datetime.now(UTC),
        )
