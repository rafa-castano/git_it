import json
from datetime import datetime

import psycopg

from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk


class PostgresEmbeddingStore:
    """Persists embedding vectors for CommitAnalysis/DiscussionEvidence summaries
    (PostgreSQL, spec 023).

    Mirrors ``SqliteEmbeddingStore`` — one row per
    ``(repository_id, source_type, source_id)``, upserted via ``ON CONFLICT ... DO UPDATE``.
    The vector is stored as a JSON-encoded array in a plain TEXT column
    (``vector_json``), not a pgvector ``vector`` column, so both backends share the
    identical schema and in-process similarity-scan code path.
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_embeddings(self, repository_id: str, items: list[EmbeddedChunk]) -> None:
        with psycopg.connect(self._conninfo) as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO embedding_vectors (
                        repository_id, source_type, source_id, text, vector_json,
                        model, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (repository_id, source_type, source_id) DO UPDATE SET
                        text        = EXCLUDED.text,
                        vector_json = EXCLUDED.vector_json,
                        model       = EXCLUDED.model,
                        created_at  = EXCLUDED.created_at
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
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT source_type, source_id, text, vector_json, model, created_at
                FROM embedding_vectors
                WHERE repository_id = %s
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
