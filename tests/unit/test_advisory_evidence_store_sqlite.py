"""Tests for SqliteAdvisoryEvidenceStore — LLM-summarized security advisory evidence
persistence (spec 026). Mirrors test_discussion_evidence_store_sqlite.py's structure.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from git_it.repository_ingestion.domain.advisories import AdvisoryEvidence
from git_it.repository_ingestion.infrastructure.sqlite import SqliteAdvisoryEvidenceStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "advisory_evidence_test.sqlite3"
    SqliteAdvisoryEvidenceStore(path).initialize()
    return path


def _make_evidence(ghsa_id: str, **overrides: Any) -> AdvisoryEvidence:
    kwargs: dict[str, Any] = {
        "ghsa_id": ghsa_id,
        "advisory_url": f"https://github.com/owner/repo/security/advisories/{ghsa_id}",
        "severity": "high",
        "summary": "summary text",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": [ghsa_id],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return AdvisoryEvidence(**kwargs)


def test_get_advisory_evidence_returns_empty_when_absent(db_path: Path) -> None:
    assert SqliteAdvisoryEvidenceStore(db_path).get_advisory_evidence("repo-1") == []


def test_save_and_get_advisory_evidence_roundtrips(db_path: Path) -> None:
    store = SqliteAdvisoryEvidenceStore(db_path)
    evidence = _make_evidence("GHSA-pmv8-rq9r-6j72")

    store.save_advisory_evidence("repo-1", [evidence])
    result = store.get_advisory_evidence("repo-1")

    assert result == [evidence]


def test_save_advisory_evidence_with_limitations_and_source_inputs(db_path: Path) -> None:
    store = SqliteAdvisoryEvidenceStore(db_path)
    evidence = _make_evidence(
        "GHSA-pmv8-rq9r-6j72",
        limitations=["low confidence"],
        source_inputs=["GHSA-pmv8-rq9r-6j72", "extra-context"],
    )

    store.save_advisory_evidence("repo-1", [evidence])
    result = store.get_advisory_evidence("repo-1")

    assert result == [evidence]


def test_save_advisory_evidence_upserts_same_ghsa_id(db_path: Path) -> None:
    store = SqliteAdvisoryEvidenceStore(db_path)
    store.save_advisory_evidence("repo-1", [_make_evidence("GHSA-pmv8-rq9r-6j72", summary="first")])

    store.save_advisory_evidence(
        "repo-1", [_make_evidence("GHSA-pmv8-rq9r-6j72", summary="second")]
    )
    result = store.get_advisory_evidence("repo-1")

    assert len(result) == 1
    assert result[0].summary == "second"


def test_unknown_repository_id_returns_empty_list(db_path: Path) -> None:
    store = SqliteAdvisoryEvidenceStore(db_path)
    store.save_advisory_evidence("repo-1", [_make_evidence("GHSA-pmv8-rq9r-6j72")])

    assert store.get_advisory_evidence("unknown-repo") == []


def test_distinct_repositories_are_independent(db_path: Path) -> None:
    store = SqliteAdvisoryEvidenceStore(db_path)
    store.save_advisory_evidence("repo-1", [_make_evidence("GHSA-pmv8-rq9r-6j72")])
    store.save_advisory_evidence("repo-2", [_make_evidence("GHSA-xxxx-yyyy-zzzz")])

    assert [e.ghsa_id for e in store.get_advisory_evidence("repo-1")] == ["GHSA-pmv8-rq9r-6j72"]
    assert [e.ghsa_id for e in store.get_advisory_evidence("repo-2")] == ["GHSA-xxxx-yyyy-zzzz"]


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteAdvisoryEvidenceStore(db_path)
    store.initialize()
    store.save_advisory_evidence("repo-1", [_make_evidence("GHSA-pmv8-rq9r-6j72")])

    assert len(store.get_advisory_evidence("repo-1")) == 1
