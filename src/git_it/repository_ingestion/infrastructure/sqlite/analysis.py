import sqlite3
from pathlib import Path

from git_it.repository_ingestion.application.ports import CaseStudyRecord, TimestampedAnalysis
from git_it.repository_ingestion.domain.analysis import CommitAnalysis


class SqliteCommitAnalysisStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commit_analyses (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id TEXT NOT NULL,
                    commit_sha    TEXT NOT NULL,
                    data          TEXT NOT NULL,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(repository_id, commit_sha)
                )
                """
            )

    def save_analysis(self, analysis: CommitAnalysis, *, repository_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO commit_analyses (repository_id, commit_sha, data)
                VALUES (?, ?, ?)
                """,
                (repository_id, analysis.commit_sha, analysis.model_dump_json()),
            )
        return cursor.rowcount == 1

    def get_analysis(self, *, repository_id: str, commit_sha: str) -> CommitAnalysis | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM commit_analyses WHERE repository_id = ? AND commit_sha = ?",
                (repository_id, commit_sha),
            ).fetchone()
        if row is None:
            return None
        analysis: CommitAnalysis = CommitAnalysis.model_validate_json(str(row[0]))
        return analysis

    def list_analyses(
        self, repository_id: str, *, limit: int | None = None
    ) -> list[CommitAnalysis]:
        query = "SELECT data FROM commit_analyses WHERE repository_id = ? ORDER BY created_at DESC"
        params: tuple[object, ...] = (repository_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (repository_id, limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CommitAnalysis.model_validate_json(str(row[0])) for row in rows]

    def list_analyses_with_dates(self, repository_id: str) -> list[TimestampedAnalysis]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ca.data, cf.committed_at
                FROM commit_analyses ca
                JOIN commit_facts cf
                  ON ca.repository_id = cf.repository_id AND ca.commit_sha = cf.sha
                WHERE ca.repository_id = ?
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
        """Return analyses saved after *since* (ISO-8601 timestamp), joined with commit dates."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ca.data, cf.committed_at
                FROM commit_analyses ca
                JOIN commit_facts cf
                  ON ca.repository_id = cf.repository_id AND ca.commit_sha = cf.sha
                WHERE ca.repository_id = ?
                  AND ca.created_at > ?
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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)


_REPO_CONTEXT_MAX_CHARS = 2000


class SqliteCaseStudyStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            # Check existing schema and migrate if needed
            existing = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='case_studies'"
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    CREATE TABLE case_studies (
                        repository_id TEXT NOT NULL,
                        audience      TEXT NOT NULL DEFAULT 'beginner',
                        narrative     TEXT NOT NULL,
                        commit_count  INTEGER NOT NULL,
                        hotspot_count INTEGER NOT NULL,
                        created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                        PRIMARY KEY (repository_id, audience)
                    )
                    """
                )
            else:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(case_studies)").fetchall()]
                if "audience" not in cols:
                    # Migrate: rebuild with composite PK, preserving existing rows as 'beginner'
                    conn.execute(
                        """
                        CREATE TABLE case_studies_v2 (
                            repository_id TEXT NOT NULL,
                            audience      TEXT NOT NULL DEFAULT 'beginner',
                            narrative     TEXT NOT NULL,
                            commit_count  INTEGER NOT NULL,
                            hotspot_count INTEGER NOT NULL,
                            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                            PRIMARY KEY (repository_id, audience)
                        )
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO case_studies_v2
                            (repository_id, audience, narrative,
                             commit_count, hotspot_count, created_at)
                        SELECT repository_id, 'beginner', narrative,
                               commit_count, hotspot_count, created_at
                        FROM case_studies
                        """
                    )
                    conn.execute("DROP TABLE case_studies")
                    conn.execute("ALTER TABLE case_studies_v2 RENAME TO case_studies")

    def save_case_study(self, record: CaseStudyRecord) -> None:
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO case_studies
                    (repository_id, audience, narrative, commit_count, hotspot_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, audience) DO UPDATE SET
                    narrative     = excluded.narrative,
                    commit_count  = excluded.commit_count,
                    hotspot_count = excluded.hotspot_count,
                    created_at    = datetime('now')
                """,
                (
                    record.repository_id,
                    record.audience,
                    record.narrative,
                    record.commit_count,
                    record.hotspot_count,
                ),
            )

    def list_available_audiences(self, repository_id: str) -> list[str]:
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT audience FROM case_studies
                WHERE repository_id = ?
                ORDER BY audience
                """,
                (repository_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def get_case_study(
        self, repository_id: str, audience: str = "beginner"
    ) -> CaseStudyRecord | None:
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT repository_id, narrative, commit_count, hotspot_count, created_at, audience
                FROM case_studies
                WHERE repository_id = ? AND audience = ?
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


class SqliteSynopsisStore:
    """Persists one audience-neutral synopsis per repository."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repository_synopsis (
                    repository_id TEXT PRIMARY KEY,
                    synopsis      TEXT NOT NULL,
                    updated_at    TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_synopsis(self, repository_id: str, synopsis: str) -> None:
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO repository_synopsis (repository_id, synopsis, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(repository_id) DO UPDATE SET
                    synopsis   = excluded.synopsis,
                    updated_at = excluded.updated_at
                """,
                (repository_id, synopsis),
            )
            conn.commit()

    def get_synopsis(self, repository_id: str) -> str | None:
        with sqlite3.connect(self._database_path) as conn:
            row = conn.execute(
                "SELECT synopsis FROM repository_synopsis WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        return str(row[0]) if row else None
