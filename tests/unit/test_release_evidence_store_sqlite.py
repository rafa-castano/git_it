"""Tests for SqliteReleaseEvidenceStore — LLM-summarized release evidence persistence
(spec 026). Mirrors test_discussion_evidence_store_sqlite.py's structure.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from git_it.repository_ingestion.domain.releases import ReleaseEvidence
from git_it.repository_ingestion.infrastructure.sqlite import SqliteReleaseEvidenceStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "release_evidence_test.sqlite3"
    SqliteReleaseEvidenceStore(path).initialize()
    return path


def _make_evidence(tag_name: str, **overrides: Any) -> ReleaseEvidence:
    kwargs: dict[str, Any] = {
        "tag_name": tag_name,
        "release_url": f"https://github.com/owner/repo/releases/tag/{tag_name}",
        "claim_type": "feature_release",
        "summary": "summary text",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": [tag_name],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return ReleaseEvidence(**kwargs)


def test_get_release_evidence_returns_empty_when_absent(db_path: Path) -> None:
    assert SqliteReleaseEvidenceStore(db_path).get_release_evidence("repo-1") == []


def test_save_and_get_release_evidence_roundtrips(db_path: Path) -> None:
    store = SqliteReleaseEvidenceStore(db_path)
    evidence = _make_evidence("v1.0.0")

    store.save_release_evidence("repo-1", [evidence])
    result = store.get_release_evidence("repo-1")

    assert result == [evidence]


def test_save_release_evidence_with_limitations_and_source_inputs(db_path: Path) -> None:
    store = SqliteReleaseEvidenceStore(db_path)
    evidence = _make_evidence(
        "v1.0.0", limitations=["low confidence"], source_inputs=["v1.0.0", "extra-context"]
    )

    store.save_release_evidence("repo-1", [evidence])
    result = store.get_release_evidence("repo-1")

    assert result == [evidence]


def test_save_release_evidence_upserts_same_tag(db_path: Path) -> None:
    store = SqliteReleaseEvidenceStore(db_path)
    store.save_release_evidence("repo-1", [_make_evidence("v1.0.0", summary="first")])

    store.save_release_evidence("repo-1", [_make_evidence("v1.0.0", summary="second")])
    result = store.get_release_evidence("repo-1")

    assert len(result) == 1
    assert result[0].summary == "second"


def test_unknown_repository_id_returns_empty_list(db_path: Path) -> None:
    store = SqliteReleaseEvidenceStore(db_path)
    store.save_release_evidence("repo-1", [_make_evidence("v1.0.0")])

    assert store.get_release_evidence("unknown-repo") == []


def test_distinct_repositories_are_independent(db_path: Path) -> None:
    store = SqliteReleaseEvidenceStore(db_path)
    store.save_release_evidence("repo-1", [_make_evidence("v1.0.0")])
    store.save_release_evidence("repo-2", [_make_evidence("v2.0.0")])

    assert [e.tag_name for e in store.get_release_evidence("repo-1")] == ["v1.0.0"]
    assert [e.tag_name for e in store.get_release_evidence("repo-2")] == ["v2.0.0"]


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteReleaseEvidenceStore(db_path)
    store.initialize()
    store.save_release_evidence("repo-1", [_make_evidence("v1.0.0")])

    assert len(store.get_release_evidence("repo-1")) == 1
