import json
from datetime import datetime

import psycopg

from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence


class PostgresAdvisoryEvidenceStore:
    """Persists LLM-summarized, schema-validated security advisory evidence
    (PostgreSQL, spec 026).

    Mirrors ``SqliteAdvisoryEvidenceStore`` — one row per
    ``(repository_id, ghsa_id)``, upserted via ``ON CONFLICT ... DO UPDATE``.
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def save_advisory_evidence(self, repository_id: str, items: list[AdvisoryEvidence]) -> None:
        with psycopg.connect(self._conninfo) as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO advisory_evidence (
                        repository_id, ghsa_id, advisory_url, severity,
                        summary, confidence, limitations, source_inputs,
                        generated_at, model
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (repository_id, ghsa_id) DO UPDATE SET
                        advisory_url   = EXCLUDED.advisory_url,
                        severity       = EXCLUDED.severity,
                        summary        = EXCLUDED.summary,
                        confidence     = EXCLUDED.confidence,
                        limitations    = EXCLUDED.limitations,
                        source_inputs  = EXCLUDED.source_inputs,
                        generated_at   = EXCLUDED.generated_at,
                        model          = EXCLUDED.model
                    """,
                    (
                        repository_id,
                        item.ghsa_id,
                        item.advisory_url,
                        item.severity,
                        item.summary,
                        item.confidence,
                        json.dumps(item.limitations),
                        json.dumps(item.source_inputs),
                        item.generated_at.isoformat(),
                        item.model,
                    ),
                )
            conn.commit()

    def get_advisory_evidence(self, repository_id: str) -> list[AdvisoryEvidence]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                """
                SELECT ghsa_id, advisory_url, severity, summary, confidence,
                       limitations, source_inputs, generated_at, model
                FROM advisory_evidence
                WHERE repository_id = %s
                """,
                (repository_id,),
            ).fetchall()
        return [
            AdvisoryEvidence(
                ghsa_id=str(row[0]),
                advisory_url=str(row[1]),
                severity=str(row[2]),  # type: ignore[arg-type]
                summary=str(row[3]),
                confidence=float(row[4]),
                limitations=json.loads(str(row[5])),
                source_inputs=json.loads(str(row[6])),
                generated_at=datetime.fromisoformat(str(row[7])),
                model=str(row[8]),
            )
            for row in rows
        ]
