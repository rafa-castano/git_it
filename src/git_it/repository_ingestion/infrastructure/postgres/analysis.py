import psycopg

from git_it.repository_ingestion.application.ports import CaseStudyRecord, TimestampedAnalysis
from git_it.repository_ingestion.domain.analysis import CommitAnalysis

_REPO_CONTEXT_MAX_CHARS = 2000


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

    def list_available_audiences(self, repository_id: str) -> list[str]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT audience FROM case_studies
                WHERE repository_id = %s
                ORDER BY audience
                """,
                (repository_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def get_repo_context(self, repository_id: str) -> str | None:
        record = self.get_case_study(repository_id, audience="beginner")
        if record is None:
            return None
        return record.narrative[:_REPO_CONTEXT_MAX_CHARS]


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
