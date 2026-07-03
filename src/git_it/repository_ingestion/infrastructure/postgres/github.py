import json
from datetime import UTC, datetime

import psycopg

from git_it.repository_ingestion.domain.github_context import GithubContext
from git_it.repository_ingestion.domain.repo_metadata import LanguageBreakdown, RepoMetadata


class PostgresGithubContextCache:
    """PostgreSQL-backed cache for GitHub context (PR + issue data) per commit SHA.

    Cache contract (mirrors SqliteGithubContextCache):
    - Row absent → never fetched (is_cached=False)
    - Row with has_github_data=0 → fetched, no PR found (get_cached returns None)
    - Row with has_github_data=1 → fetched, PR found (get_cached returns GithubContext)
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def is_cached(self, repository_id: str, commit_sha: str) -> bool:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT 1 FROM github_context WHERE repository_id = %s AND commit_sha = %s",
                (repository_id, commit_sha),
            ).fetchone()
        return row is not None

    def get_cached(self, repository_id: str, commit_sha: str) -> GithubContext | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                """
                SELECT pr_number, pr_title, pr_body, issue_numbers, issue_bodies, has_github_data
                FROM github_context
                WHERE repository_id = %s AND commit_sha = %s
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
        fetched_at = datetime.now(UTC).isoformat()
        has_data = context is not None and context.has_pr
        pr_number = context.pr_number if context is not None else None
        pr_title = context.pr_title if context is not None else None
        pr_body = context.pr_body if context is not None else None
        issue_numbers = json.dumps(list(context.issue_numbers)) if context is not None else "[]"
        issue_bodies = json.dumps(list(context.issue_bodies)) if context is not None else "[]"
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO github_context (
                    repository_id, commit_sha, pr_number, pr_title, pr_body,
                    issue_numbers, issue_bodies, has_github_data, fetched_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (repository_id, commit_sha) DO NOTHING
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
            conn.commit()


class PostgresRepoMetadataStore:
    """Persists one GitHub stars + language-breakdown row per repository (PostgreSQL)."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_repo_metadata(self, repository_id: str, metadata: RepoMetadata) -> None:
        languages_json = json.dumps(
            [{"language": lang.language, "bytes": lang.bytes} for lang in metadata.languages]
        )
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO repo_metadata (repository_id, stars, languages, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (repository_id) DO UPDATE SET
                    stars      = EXCLUDED.stars,
                    languages  = EXCLUDED.languages,
                    updated_at = EXCLUDED.updated_at
                """,
                (repository_id, metadata.stars, languages_json),
            )
            conn.commit()

    def get_repo_metadata(self, repository_id: str) -> RepoMetadata | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT stars, languages FROM repo_metadata WHERE repository_id = %s",
                (repository_id,),
            ).fetchone()
        if row is None:
            return None
        languages = tuple(
            LanguageBreakdown(language=str(item["language"]), bytes=int(item["bytes"]))
            for item in json.loads(str(row[1]))
        )
        return RepoMetadata(stars=int(row[0]), languages=languages)


class PostgresDefaultBranchStore:
    """Persists the default branch captured from a repository's local clone (PostgreSQL, spec 020).

    Deliberately a new, independent table from ``repo_metadata`` — see
    ``SqliteDefaultBranchStore`` for the rationale (token-independent capture
    vs. spec 019's NOT NULL, token-gated stars column).
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_default_branch(self, repository_id: str, default_branch: str) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO default_branch_metadata (repository_id, default_branch, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (repository_id) DO UPDATE SET
                    default_branch = EXCLUDED.default_branch,
                    updated_at     = EXCLUDED.updated_at
                """,
                (repository_id, default_branch),
            )
            conn.commit()

    def get_default_branch(self, repository_id: str) -> str | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT default_branch FROM default_branch_metadata WHERE repository_id = %s",
                (repository_id,),
            ).fetchone()
        return str(row[0]) if row is not None else None
