import json
from datetime import datetime

import psycopg

from git_it.repository_ingestion.domain.releases import ReleaseEvidence


class PostgresReleaseEvidenceStore:
    """Persists LLM-summarized, schema-validated release evidence (PostgreSQL, spec 026).

    Mirrors ``SqliteReleaseEvidenceStore`` — one row per
    ``(repository_id, tag_name)``, upserted via ``ON CONFLICT ... DO UPDATE``.
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_release_evidence(self, repository_id: str, items: list[ReleaseEvidence]) -> None:
        with psycopg.connect(self._conninfo) as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO release_evidence (
                        repository_id, tag_name, release_url, claim_type,
                        summary, confidence, limitations, source_inputs,
                        generated_at, model
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (repository_id, tag_name) DO UPDATE SET
                        release_url    = EXCLUDED.release_url,
                        claim_type     = EXCLUDED.claim_type,
                        summary        = EXCLUDED.summary,
                        confidence     = EXCLUDED.confidence,
                        limitations    = EXCLUDED.limitations,
                        source_inputs  = EXCLUDED.source_inputs,
                        generated_at   = EXCLUDED.generated_at,
                        model          = EXCLUDED.model
                    """,
                    (
                        repository_id,
                        item.tag_name,
                        item.release_url,
                        item.claim_type,
                        item.summary,
                        item.confidence,
                        json.dumps(item.limitations),
                        json.dumps(item.source_inputs),
                        item.generated_at.isoformat(),
                        item.model,
                    ),
                )
            conn.commit()

    def get_release_evidence(self, repository_id: str) -> list[ReleaseEvidence]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT tag_name, release_url, claim_type, summary, confidence,
                       limitations, source_inputs, generated_at, model
                FROM release_evidence
                WHERE repository_id = %s
                """,
                (repository_id,),
            ).fetchall()
        return [
            ReleaseEvidence(
                tag_name=str(row[0]),
                release_url=str(row[1]),
                claim_type=str(row[2]),  # type: ignore[arg-type]
                summary=str(row[3]),
                confidence=float(row[4]),
                limitations=json.loads(str(row[5])),
                source_inputs=json.loads(str(row[6])),
                generated_at=datetime.fromisoformat(str(row[7])),
                model=str(row[8]),
            )
            for row in rows
        ]
