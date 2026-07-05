import json
import sqlite3
from datetime import datetime
from pathlib import Path

from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk


class SqliteEmbeddingStore:
    """Persists embedding vectors for CommitAnalysis/DiscussionEvidence summaries (spec 023).

    One row per ``(repository_id, source_type, source_id)``, upserted. The vector is
    stored as a JSON-encoded array in a plain TEXT column (``vector_json``) —
    deliberately not a Postgres-specific ``vector`` column type, so both backends use
    the identical schema and the identical in-process similarity-scan code path.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embedding_vectors (
                    repository_id TEXT NOT NULL,
                    source_type   TEXT NOT NULL,
                    source_id     TEXT NOT NULL,
                    text          TEXT NOT NULL,
                    vector_json   TEXT NOT NULL,
                    model         TEXT NOT NULL,
                    created_at    TEXT NOT NULL,
                    PRIMARY KEY (repository_id, source_type, source_id)
                )
                """
            )
            conn.commit()

    def save_embeddings(self, repository_id: str, items: list[EmbeddedChunk]) -> None:
        with sqlite3.connect(self._database_path) as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO embedding_vectors (
                        repository_id, source_type, source_id, text, vector_json,
                        model, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repository_id, source_type, source_id) DO UPDATE SET
                        text        = excluded.text,
                        vector_json = excluded.vector_json,
                        model       = excluded.model,
                        created_at  = excluded.created_at
                    """,
                    (
                        repository_id,
                        item.source_type,
                        item.source_id,
                        item.text,
                        json.dumps(item.vector),
                        item.model,
                        item.created_at.isoformat(),
                    ),
                )
            conn.commit()

    def get_all_embeddings(self, repository_id: str) -> list[EmbeddedChunk]:
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT source_type, source_id, text, vector_json, model, created_at
                FROM embedding_vectors
                WHERE repository_id = ?
                """,
                (repository_id,),
            ).fetchall()
        return [
            EmbeddedChunk(
                repository_id=repository_id,
                source_type=str(row[0]),  # type: ignore[arg-type]
                source_id=str(row[1]),
                text=str(row[2]),
                vector=json.loads(str(row[3])),
                model=str(row[4]),
                created_at=datetime.fromisoformat(str(row[5])),
            )
            for row in rows
        ]
