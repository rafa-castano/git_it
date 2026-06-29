"""PostgreSQL adapters — mirrors sqlite.py but uses psycopg (v3).

All adapters use connection-per-operation (no pooling), matching the SQLite pattern.
Placeholders use %s (psycopg3 style, not ? as in sqlite3).
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import psycopg.rows

from git_it.repository_ingestion.application.commit_query_service import CommitRecord
from git_it.repository_ingestion.application.ports import (
    CaseStudyRecord,
    CommitPersistenceResult,
    CommitSummaryRecord,
    CommitWithAnalysisRecord,
    ContributorRecord,
    FileChurnRecord,
    FileOwnershipRecord,
    IngestionRunRecord,
    RepositoryRecord,
    TimestampedAnalysis,
)
from git_it.repository_ingestion.domain.analysis import CommitAnalysis
from git_it.repository_ingestion.domain.commits import ExtractedCommit
from git_it.repository_ingestion.domain.github_context import GithubContext


def initialize(conninfo: str) -> None:
    """Run migrations/001_initial.sql against the given PostgreSQL connection string."""
    migrations_path = Path(__file__).parents[5] / "migrations" / "001_initial.sql"
    sql = migrations_path.read_text(encoding="utf-8")
    with psycopg.connect(conninfo) as conn:
        conn.execute(sql)
        conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _int_to_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _record_from_row(row: tuple[object, ...]) -> IngestionRunRecord:
    return IngestionRunRecord(
        run_id=str(row[0]),
        repository_id=str(row[1]),
        canonical_url=str(row[2]),
        status=str(row[3]),
        started_at=str(row[4]),
        completed_at=_optional_str(row[5]),
        error_code=_optional_str(row[6]),
        error_stage=_optional_str(row[7]),
        retryable=_int_to_bool(row[8]),
        safe_message=_optional_str(row[9]),
    )


_BOT_PATTERN = re.compile(r"\[bot\]|dependabot|copilot|renovate", re.IGNORECASE)


def _extract_github_username(email: str) -> str | None:
    m = re.match(r"^\d+\+(.+)@users\.noreply\.github\.com$", email or "")
    if m:
        return m.group(1)
    m = re.match(r"^([^@+]+)@users\.noreply\.github\.com$", email or "")
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Ingestion run store
# ---------------------------------------------------------------------------


class PostgresIngestionRunStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_ingestion_run(self, record: IngestionRunRecord) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO ingestion_runs (
                    run_id, repository_id, canonical_url, status, started_at,
                    completed_at, error_code, error_stage, retryable, safe_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.run_id,
                    record.repository_id,
                    record.canonical_url,
                    record.status,
                    record.started_at,
                    record.completed_at,
                    record.error_code,
                    record.error_stage,
                    _bool_to_int(record.retryable),
                    record.safe_message,
                ),
            )
            conn.commit()

    def get_ingestion_run(self, run_id: str) -> IngestionRunRecord | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                """
                SELECT run_id, repository_id, canonical_url, status, started_at,
                       completed_at, error_code, error_stage, retryable, safe_message
                FROM ingestion_runs
                WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return _record_from_row(row)

    def list_ingestion_runs_for_repository(
        self,
        repository_id: str,
    ) -> list[IngestionRunRecord]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT run_id, repository_id, canonical_url, status, started_at,
                       completed_at, error_code, error_stage, retryable, safe_message
                FROM ingestion_runs
                WHERE repository_id = %s
                ORDER BY started_at ASC, run_id ASC
                """,
                (repository_id,),
            ).fetchall()
        return [_record_from_row(row) for row in rows]


# ---------------------------------------------------------------------------
# Commit fact store
# ---------------------------------------------------------------------------


class PostgresCommitStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_commit_facts(
        self,
        commits: list[ExtractedCommit],
        *,
        repository_id: str,
    ) -> CommitPersistenceResult:
        inserted = 0
        reused = 0
        with psycopg.connect(self._conninfo) as conn:
            for commit in commits:
                cursor = conn.execute(
                    """
                    INSERT INTO commit_facts (
                        repository_id, sha, committed_at, message,
                        author_name, committer_name, parent_shas, author_email
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (repository_id, sha) DO NOTHING
                    """,
                    (
                        repository_id,
                        commit.sha,
                        commit.committed_at,
                        commit.message,
                        commit.author_name,
                        commit.committer_name,
                        json.dumps(list(commit.parent_shas)),
                        commit.author_email,
                    ),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    reused += 1
            conn.commit()
        return CommitPersistenceResult(inserted=inserted, reused=reused)


# ---------------------------------------------------------------------------
# File fact store
# ---------------------------------------------------------------------------


class PostgresFileFactStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_file_facts(
        self,
        commits: list[ExtractedCommit],
        *,
        repository_id: str,
    ) -> CommitPersistenceResult:
        inserted = 0
        reused = 0
        with psycopg.connect(self._conninfo) as conn:
            for commit in commits:
                for change in commit.file_changes:
                    cursor = conn.execute(
                        """
                        INSERT INTO file_facts (
                            repository_id, commit_sha, file_path, insertions, deletions
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (repository_id, commit_sha, file_path) DO NOTHING
                        """,
                        (
                            repository_id,
                            commit.sha,
                            change.path,
                            change.insertions,
                            change.deletions,
                        ),
                    )
                    if cursor.rowcount == 1:
                        inserted += 1
                    else:
                        reused += 1
            conn.commit()
        return CommitPersistenceResult(inserted=inserted, reused=reused)


# ---------------------------------------------------------------------------
# Commit reader
# ---------------------------------------------------------------------------


class PostgresCommitReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def get_commit_date_map(self, repository_id: str) -> dict[str, str]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT sha, committed_at FROM commit_facts WHERE repository_id = %s",
                (repository_id,),
            ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def list_commit_messages(self, repository_id: str) -> list[CommitSummaryRecord]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT sha, message FROM commit_facts WHERE repository_id = %s",
                (repository_id,),
            ).fetchall()
        return [CommitSummaryRecord(sha=str(row[0]), message=str(row[1])) for row in rows]

    def list_commits_for_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        order: str = "newest",
        since: str | None = None,
        until: str | None = None,
    ) -> list[CommitRecord]:
        if order not in ("newest", "oldest"):
            raise ValueError(f"Invalid order value: {order!r}")
        order_dir = "ASC" if order == "oldest" else "DESC"
        conditions = ["repository_id = %s"]
        params: list[object] = [repository_id]
        if since is not None:
            conditions.append("SUBSTR(committed_at, 1, 10) >= %s")
            params.append(since)
        if until is not None:
            conditions.append("SUBSTR(committed_at, 1, 10) <= %s")
            params.append(until)
        where = " AND ".join(conditions)
        query = f"""
            SELECT sha, committed_at, message, author_name, committer_name, parent_shas
            FROM commit_facts
            WHERE {where}
            ORDER BY committed_at {order_dir}
        """
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            CommitRecord(
                repository_id=repository_id,
                sha=str(row[0]),
                committed_at=str(row[1]),
                message=str(row[2]),
                author_name=str(row[3]),
                committer_name=str(row[4]),
                parent_shas=tuple(json.loads(str(row[5]))),
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Commit analysis store
# ---------------------------------------------------------------------------


class PostgresCommitAnalysisStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_analysis(self, analysis: CommitAnalysis, *, repository_id: str) -> bool:
        with psycopg.connect(self._conninfo) as conn:
            cursor = conn.execute(
                """
                INSERT INTO commit_analyses (repository_id, commit_sha, data)
                VALUES (%s, %s, %s)
                ON CONFLICT (repository_id, commit_sha) DO NOTHING
                """,
                (repository_id, analysis.commit_sha, analysis.model_dump_json()),
            )
            conn.commit()
        return (cursor.rowcount or 0) == 1

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT data FROM commit_analyses WHERE repository_id = %s AND commit_sha = %s",
                (repository_id, commit_sha),
            ).fetchone()
        if row is None:
            return None
        analysis: CommitAnalysis = CommitAnalysis.model_validate_json(str(row[0]))
        return analysis

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        query = "SELECT data FROM commit_analyses WHERE repository_id = %s ORDER BY created_at DESC"
        params: tuple[object, ...] = (repository_id,)
        if limit is not None:
            query += " LIMIT %s"
            params = (repository_id, limit)
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(query, params).fetchall()
        return [CommitAnalysis.model_validate_json(str(row[0])) for row in rows]

    def list_analyses_with_dates(self, repository_id: str) -> list[TimestampedAnalysis]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT ca.data, cf.committed_at
                FROM commit_analyses ca
                JOIN commit_facts cf
                  ON ca.repository_id = cf.repository_id AND ca.commit_sha = cf.sha
                WHERE ca.repository_id = %s
                ORDER BY cf.committed_at ASC
                """,
                (repository_id,),
            ).fetchall()
        return [
            TimestampedAnalysis(
                analysis=CommitAnalysis.model_validate_json(str(row[0])),
                committed_at=str(row[1]),
            )
            for row in rows
        ]

    def list_analyses_since(self, repository_id: str, *, since: str) -> list[TimestampedAnalysis]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT ca.data, cf.committed_at
                FROM commit_analyses ca
                JOIN commit_facts cf
                  ON ca.repository_id = cf.repository_id AND ca.commit_sha = cf.sha
                WHERE ca.repository_id = %s
                  AND ca.created_at > %s
                ORDER BY cf.committed_at ASC
                """,
                (repository_id, since),
            ).fetchall()
        return [
            TimestampedAnalysis(
                analysis=CommitAnalysis.model_validate_json(str(row[0])),
                committed_at=str(row[1]),
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# File fact reader
# ---------------------------------------------------------------------------


class PostgresFileFactReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def get_file_churn(self, repository_id: str) -> list[FileChurnRecord]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT
                    file_path,
                    COUNT(DISTINCT commit_sha) AS commit_count,
                    SUM(insertions)            AS total_insertions,
                    SUM(deletions)             AS total_deletions
                FROM file_facts
                WHERE repository_id = %s
                GROUP BY file_path
                ORDER BY commit_count DESC
                """,
                (repository_id,),
            ).fetchall()
        return [
            FileChurnRecord(
                file_path=str(row[0]),
                commit_count=int(row[1]),
                total_insertions=int(row[2]),
                total_deletions=int(row[3]),
            )
            for row in rows
        ]

    def get_file_evidence_commits(
        self, repository_id: str, *, limit: int = 5
    ) -> dict[str, tuple[str, ...]]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT f.file_path, c.sha
                FROM file_facts f
                JOIN commit_facts c ON c.sha = f.commit_sha AND c.repository_id = f.repository_id
                WHERE f.repository_id = %s
                ORDER BY f.file_path, c.committed_at DESC
                """,
                (repository_id,),
            ).fetchall()
        result: dict[str, list[str]] = {}
        for file_path, sha in rows:
            fp = str(file_path)
            bucket = result.setdefault(fp, [])
            if len(bucket) < limit:
                bucket.append(str(sha))
        return {fp: tuple(shas) for fp, shas in result.items()}

    def get_file_ownership(self, repository_id: str) -> list[FileOwnershipRecord]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT
                    ff.file_path,
                    COUNT(DISTINCT cf.author_name) AS author_count,
                    COUNT(DISTINCT ff.commit_sha)  AS commit_count
                FROM file_facts ff
                JOIN commit_facts cf
                  ON ff.repository_id = cf.repository_id AND ff.commit_sha = cf.sha
                WHERE ff.repository_id = %s
                GROUP BY ff.file_path
                """,
                (repository_id,),
            ).fetchall()
        return [
            FileOwnershipRecord(
                file_path=str(row[0]),
                author_count=int(row[1]),
                commit_count=int(row[2]),
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Case study store
# ---------------------------------------------------------------------------

_REPO_CONTEXT_MAX_CHARS = 2000


class PostgresCaseStudyStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_case_study(self, record: CaseStudyRecord) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO case_studies
                    (repository_id, audience, narrative, commit_count, hotspot_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (repository_id, audience) DO UPDATE SET
                    narrative     = EXCLUDED.narrative,
                    commit_count  = EXCLUDED.commit_count,
                    hotspot_count = EXCLUDED.hotspot_count,
                    created_at    = TO_CHAR(
                        NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'
                    )
                """,
                (
                    record.repository_id,
                    record.audience,
                    record.narrative,
                    record.commit_count,
                    record.hotspot_count,
                ),
            )
            conn.commit()

    def get_case_study(
        self, repository_id: str, audience: str = "beginner"
    ) -> CaseStudyRecord | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                """
                SELECT repository_id, narrative, commit_count, hotspot_count, created_at, audience
                FROM case_studies
                WHERE repository_id = %s AND audience = %s
                """,
                (repository_id, audience),
            ).fetchone()
        if row is None:
            return None
        return CaseStudyRecord(
            repository_id=str(row[0]),
            narrative=str(row[1]),
            commit_count=int(row[2]),
            hotspot_count=int(row[3]),
            generated_at=str(row[4]),
            audience=str(row[5]),
        )

    def get_repo_context(self, repository_id: str) -> str | None:
        record = self.get_case_study(repository_id, audience="beginner")
        if record is None:
            return None
        return record.narrative[:_REPO_CONTEXT_MAX_CHARS]


# ---------------------------------------------------------------------------
# Repository list reader
# ---------------------------------------------------------------------------


class PostgresRepositoryListReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def list_repositories(self) -> list[RepositoryRecord]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT
                    ir.repository_id,
                    ir.canonical_url,
                    ir.status,
                    COUNT(DISTINCT cf.sha)  AS commit_count,
                    COUNT(DISTINCT ca.id)   AS analysis_count,
                    MAX(CASE WHEN cs.repository_id IS NOT NULL THEN 1 ELSE 0 END) AS has_case_study
                FROM ingestion_runs ir
                LEFT JOIN commit_facts cf ON cf.repository_id = ir.repository_id
                LEFT JOIN commit_analyses ca ON ca.repository_id = ir.repository_id
                LEFT JOIN case_studies cs ON cs.repository_id = ir.repository_id
                GROUP BY ir.repository_id, ir.canonical_url, ir.status
                ORDER BY ir.repository_id
                """
            ).fetchall()
        return [
            RepositoryRecord(
                repository_id=str(row[0]),
                canonical_url=str(row[1]),
                status=str(row[2]),
                commit_count=int(row[3]),
                analysis_count=int(row[4]),
                has_case_study=bool(row[5]),
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Commit count reader
# ---------------------------------------------------------------------------


class PostgresCommitCountReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def count_commits(self, repository_id: str) -> int:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM commit_facts WHERE repository_id = %s",
                (repository_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def count_analyses(self, repository_id: str) -> int:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM commit_analyses WHERE repository_id = %s",
                (repository_id,),
            ).fetchone()
        return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Commit with analysis reader
# ---------------------------------------------------------------------------


class PostgresCommitWithAnalysisReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def list_commits_with_analyses(
        self,
        repository_id: str,
        *,
        limit: int,
        order: str = "newest",
    ) -> list[CommitWithAnalysisRecord]:
        if order not in ("newest", "oldest"):
            raise ValueError(f"Invalid order value: {order!r}")
        order_dir = "ASC" if order == "oldest" else "DESC"
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                f"""
                SELECT cf.sha, cf.message, cf.committed_at, ca.data
                FROM commit_analyses ca
                JOIN commit_facts cf
                  ON cf.sha = ca.commit_sha AND cf.repository_id = ca.repository_id
                WHERE ca.repository_id = %s
                ORDER BY cf.committed_at {order_dir}
                LIMIT %s
                """,
                (repository_id, limit),
            ).fetchall()
        return [
            CommitWithAnalysisRecord(
                sha=str(row[0]),
                message=str(row[1]),
                committed_at=str(row[2]),
                analysis_data=str(row[3]) if row[3] is not None else None,
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Contributor reader
# ---------------------------------------------------------------------------


class PostgresContributorReader:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def list_contributors(self, repository_id: str) -> list[ContributorRecord]:
        with psycopg.connect(self._conninfo) as conn:
            cur = conn.cursor()

            # Per-author commit stats
            cur.execute(
                """
                SELECT author_name,
                       COUNT(*) AS commit_count,
                       MIN(committed_at) AS first_commit,
                       MAX(committed_at) AS last_commit,
                       COUNT(DISTINCT SUBSTR(committed_at, 1, 10)) AS active_days,
                       MAX(author_email) AS author_email
                FROM commit_facts
                WHERE repository_id = %s
                GROUP BY author_name
                ORDER BY commit_count DESC
                """,
                (repository_id,),
            )
            author_rows = cur.fetchall()

            if not author_rows:
                return []

            # Category breakdown per author — use JSON path operator
            cur.execute(
                """
                SELECT cf.author_name,
                       ca.data::json->>'category' AS category,
                       COUNT(*) AS cnt
                FROM commit_facts cf
                JOIN commit_analyses ca ON ca.repository_id = cf.repository_id
                                        AND ca.commit_sha = cf.sha
                WHERE cf.repository_id = %s
                GROUP BY cf.author_name, category
                """,
                (repository_id,),
            )
            cat_rows = cur.fetchall()
            cat_by_author: dict[str, dict[str, int]] = {}
            for author, cat, cnt in cat_rows:
                if author not in cat_by_author:
                    cat_by_author[author] = {}
                if cat:
                    cat_by_author[author][cat.upper()] = cnt

            # Top files per author
            cur.execute(
                """
                SELECT cf.author_name, ff.file_path, COUNT(*) AS touches
                FROM commit_facts cf
                JOIN file_facts ff ON ff.repository_id = cf.repository_id
                                   AND ff.commit_sha = cf.sha
                WHERE cf.repository_id = %s
                GROUP BY cf.author_name, ff.file_path
                ORDER BY cf.author_name, touches DESC
                """,
                (repository_id,),
            )
            file_rows = cur.fetchall()
            files_by_author: dict[str, list[str]] = {}
            for author, fpath, _ in file_rows:
                if author not in files_by_author:
                    files_by_author[author] = []
                if len(files_by_author[author]) < 5:
                    files_by_author[author].append(fpath)

        return [
            ContributorRecord(
                author_name=name,
                commit_count=count,
                first_commit=(first[:10] if first else None),
                last_commit=(last[:10] if last else None),
                is_bot=bool(_BOT_PATTERN.search(name or "")),
                active_days=active_days,
                github_username=_extract_github_username(email or ""),
                category_counts=cat_by_author.get(name, {}),
                top_files=files_by_author.get(name, []),
            )
            for name, count, first, last, active_days, email in author_rows
        ]


# ---------------------------------------------------------------------------
# GitHub context cache
# ---------------------------------------------------------------------------


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


class PostgresSynopsisStore:
    """Persists one audience-neutral synopsis per repository (PostgreSQL)."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_synopsis(self, repository_id: str, synopsis: str) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                """
                INSERT INTO repository_synopsis (repository_id, synopsis, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (repository_id) DO UPDATE SET
                    synopsis   = EXCLUDED.synopsis,
                    updated_at = EXCLUDED.updated_at
                """,
                (repository_id, synopsis),
            )
            conn.commit()

    def get_synopsis(self, repository_id: str) -> str | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT synopsis FROM repository_synopsis WHERE repository_id = %s",
                (repository_id,),
            ).fetchone()
        return str(row[0]) if row else None
