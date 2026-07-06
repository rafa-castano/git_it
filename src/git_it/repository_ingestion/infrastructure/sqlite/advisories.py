import json
import sqlite3
from datetime import datetime
from pathlib import Path

from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence


class SqliteAdvisoryEvidenceStore:
    """Persists LLM-summarized, schema-validated security advisory evidence (spec 026).

    One row per ``(repository_id, ghsa_id)``, upserted. Raw advisory text
    (``SecurityAdvisory.description``) never reaches this store — only the
    validated ``AdvisoryEvidence`` output does. A missing repository_id simply
    means "no qualifying advisories were summarized for this repository" (no
    token, non-GitHub URL, zero qualifying advisories, or a pre-existing
    repository ingested before this feature shipped) — mirroring the "missing
    row" contract already used by ``SqliteDiscussionEvidenceStore``.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS advisory_evidence (
                    repository_id  TEXT NOT NULL,
                    ghsa_id        TEXT NOT NULL,
                    advisory_url   TEXT NOT NULL,
                    severity       TEXT NOT NULL,
                    summary        TEXT NOT NULL,
                    confidence     REAL NOT NULL,
                    limitations    TEXT NOT NULL DEFAULT '[]',
                    source_inputs  TEXT NOT NULL DEFAULT '[]',
                    generated_at   TEXT NOT NULL,
                    model          TEXT NOT NULL,
                    PRIMARY KEY (repository_id, ghsa_id)
                )
                """
            )
            conn.commit()

    def save_advisory_evidence(self, repository_id: str, items: list[AdvisoryEvidence]) -> None:
        with sqlite3.connect(self._database_path) as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO advisory_evidence (
                        repository_id, ghsa_id, advisory_url, severity,
                        summary, confidence, limitations, source_inputs,
                        generated_at, model
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repository_id, ghsa_id) DO UPDATE SET
                        advisory_url   = excluded.advisory_url,
                        severity       = excluded.severity,
                        summary        = excluded.summary,
                        confidence     = excluded.confidence,
                        limitations    = excluded.limitations,
                        source_inputs  = excluded.source_inputs,
                        generated_at   = excluded.generated_at,
                        model          = excluded.model
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
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT ghsa_id, advisory_url, severity, summary, confidence,
                       limitations, source_inputs, generated_at, model
                FROM advisory_evidence
                WHERE repository_id = ?
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
