import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown, RepoMetadata


class SqliteGithubContextCache:
    """SQLite-backed cache for GitHub context (PR + issue data) per commit SHA.

    Cache contract:
    - Row absent → never fetched (is_cached=False)
    - Row with has_github_data=0 → fetched, no PR found (get_cached returns None)
    - Row with has_github_data=1 → fetched, PR found (get_cached returns GithubContext)
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS github_context (
                    repository_id TEXT NOT NULL,
                    commit_sha    TEXT NOT NULL,
                    pr_number     INTEGER,
                    pr_title      TEXT,
                    pr_body       TEXT,
                    issue_numbers TEXT NOT NULL DEFAULT '[]',
                    issue_bodies  TEXT NOT NULL DEFAULT '[]',
                    has_github_data INTEGER NOT NULL DEFAULT 0,
                    fetched_at    TEXT NOT NULL,
                    PRIMARY KEY (repository_id, commit_sha)
                )
                """
            )

    def is_cached(self, repository_id: str, commit_sha: str) -> bool:
        """Return True if a fetch attempt has already been recorded for this commit."""
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM github_context WHERE repository_id = ? AND commit_sha = ?",
                (repository_id, commit_sha),
            ).fetchone()
        return row is not None

    def get_cached(self, repository_id: str, commit_sha: str) -> GithubContext | None:
        """Return cached GithubContext, or None if no PR was found (or row absent)."""
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT pr_number, pr_title, pr_body, issue_numbers, issue_bodies, has_github_data
                FROM github_context
                WHERE repository_id = ? AND commit_sha = ?
                """,
                (repository_id, commit_sha),
            ).fetchone()
        if row is None:
            return None
        has_data = bool(row[5])
        if not has_data:
            return None
        return GithubContext(
            pr_number=int(row[0]) if row[0] is not None else None,
            pr_title=str(row[1]) if row[1] is not None else None,
            pr_body=str(row[2]) if row[2] is not None else None,
            issue_numbers=tuple(json.loads(str(row[3]))),
            issue_bodies=tuple(json.loads(str(row[4]))),
            has_pr=True,
        )

    def save(self, repository_id: str, commit_sha: str, context: GithubContext | None) -> None:
        """Persist the fetch result. context=None means 'fetched, no PR found'."""
        fetched_at = datetime.now(UTC).isoformat()
        has_data = context is not None and context.has_pr
        pr_number = context.pr_number if context is not None else None
        pr_title = context.pr_title if context is not None else None
        pr_body = context.pr_body if context is not None else None
        issue_numbers = json.dumps(list(context.issue_numbers)) if context is not None else "[]"
        issue_bodies = json.dumps(list(context.issue_bodies)) if context is not None else "[]"
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO github_context (
                    repository_id, commit_sha, pr_number, pr_title, pr_body,
                    issue_numbers, issue_bodies, has_github_data, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repository_id,
                    commit_sha,
                    pr_number,
                    pr_title,
                    pr_body,
                    issue_numbers,
                    issue_bodies,
                    1 if has_data else 0,
                    fetched_at,
                ),
            )


class SqliteRepoMetadataStore:
    """Persists one GitHub stars + language-breakdown row per repository.

    Fetched at most once per ingestion (see GithubRepoMetadataFetcher) — this
    store has no cache-miss/negative-cache distinction like SqliteGithubContextCache;
    a missing row simply means "never fetched" (no token, non-GitHub URL, fetch
    failure, or pre-existing repo ingested before this feature shipped).
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repo_metadata (
                    repository_id TEXT PRIMARY KEY,
                    stars         INTEGER NOT NULL,
                    languages     TEXT NOT NULL DEFAULT '[]',
                    updated_at    TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_repo_metadata(self, repository_id: str, metadata: RepoMetadata) -> None:
        languages_json = json.dumps(
            [{"language": lang.language, "bytes": lang.bytes} for lang in metadata.languages]
        )
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO repo_metadata (repository_id, stars, languages, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(repository_id) DO UPDATE SET
                    stars      = excluded.stars,
                    languages  = excluded.languages,
                    updated_at = excluded.updated_at
                """,
                (repository_id, metadata.stars, languages_json),
            )
            conn.commit()

    def get_repo_metadata(self, repository_id: str) -> RepoMetadata | None:
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                "SELECT stars, languages FROM repo_metadata WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        if row is None:
            return None
        languages = tuple(
            LanguageBreakdown(language=str(item["language"]), bytes=int(item["bytes"]))
            for item in json.loads(str(row[1]))
        )
        return RepoMetadata(stars=int(row[0]), languages=languages)


class SqliteDefaultBranchStore:
    """Persists the default branch captured from a repository's local clone (spec 020).

    Deliberately a new, independent table from ``repo_metadata`` (spec 019's
    stars/languages store): that table's ``stars`` column is NOT NULL because
    it is only ever written together with a successful, token-gated GitHub
    stars fetch. Default-branch capture must work with GITHUB_TOKEN unset, so
    it gets its own table rather than forcing a NOT NULL relaxation onto an
    already-shipped, unrelated contract. A missing row means "not yet
    captured" (pre-existing repository, or HEAD could not be resolved at
    ingestion time) — the frontend simply does not linkify paths for that
    repository.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS default_branch_metadata (
                    repository_id  TEXT PRIMARY KEY,
                    default_branch TEXT NOT NULL,
                    updated_at     TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_default_branch(self, repository_id: str, default_branch: str) -> None:
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO default_branch_metadata (repository_id, default_branch, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(repository_id) DO UPDATE SET
                    default_branch = excluded.default_branch,
                    updated_at     = excluded.updated_at
                """,
                (repository_id, default_branch),
            )
            conn.commit()

    def get_default_branch(self, repository_id: str) -> str | None:
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                "SELECT default_branch FROM default_branch_metadata WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        return str(row[0]) if row is not None else None
