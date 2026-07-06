import json
import sqlite3
from datetime import datetime
from pathlib import Path

from git_it.repository_ingestion.domain.releases import ReleaseEvidence


class SqliteReleaseEvidenceStore:
    """Persists LLM-summarized, schema-validated release evidence (spec 026).

    One row per ``(repository_id, tag_name)``, upserted. Raw release-notes text
    (``Release.body``) never reaches this store — only the validated
    ``ReleaseEvidence`` output does. A missing repository_id simply means "no
    qualifying releases were summarized for this repository" (no token,
    non-GitHub URL, zero qualifying releases, or a pre-existing repository
    ingested before this feature shipped) — mirroring the "missing row"
    contract already used by ``SqliteDiscussionEvidenceStore``.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS release_evidence (
                    repository_id  TEXT NOT NULL,
                    tag_name       TEXT NOT NULL,
                    release_url    TEXT NOT NULL,
                    claim_type     TEXT NOT NULL,
                    summary        TEXT NOT NULL,
                    confidence     REAL NOT NULL,
                    limitations    TEXT NOT NULL DEFAULT '[]',
                    source_inputs  TEXT NOT NULL DEFAULT '[]',
                    generated_at   TEXT NOT NULL,
                    model          TEXT NOT NULL,
                    PRIMARY KEY (repository_id, tag_name)
                )
                """
            )
            conn.commit()

    def save_release_evidence(self, repository_id: str, items: list[ReleaseEvidence]) -> None:
        with sqlite3.connect(self._database_path) as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO release_evidence (
                        repository_id, tag_name, release_url, claim_type,
                        summary, confidence, limitations, source_inputs,
                        generated_at, model
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repository_id, tag_name) DO UPDATE SET
                        release_url    = excluded.release_url,
                        claim_type     = excluded.claim_type,
                        summary        = excluded.summary,
                        confidence     = excluded.confidence,
                        limitations    = excluded.limitations,
                        source_inputs  = excluded.source_inputs,
                        generated_at   = excluded.generated_at,
                        model          = excluded.model
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
        with sqlite3.connect(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT tag_name, release_url, claim_type, summary, confidence,
                       limitations, source_inputs, generated_at, model
                FROM release_evidence
                WHERE repository_id = ?
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
