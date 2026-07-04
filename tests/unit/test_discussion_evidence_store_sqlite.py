"""Tests for SqliteDiscussionEvidenceStore — LLM-summarized discussion evidence persistence
(spec 022). Mirrors test_repo_metadata_store_sqlite.py's structure.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from git_it.repository_ingestion.domain.discussions import DiscussionEvidence
from git_it.repository_ingestion.infrastructure.sqlite import SqliteDiscussionEvidenceStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "discussion_evidence_test.sqlite3"
    SqliteDiscussionEvidenceStore(path).initialize()
    return path


def _make_evidence(discussion_id: str, number: int, **overrides: Any) -> DiscussionEvidence:
    kwargs: dict[str, Any] = {
        "discussion_id": discussion_id,
        "discussion_url": f"https://github.com/owner/repo/discussions/{number}",
        "claim_type": "design_rationale",
        "summary": "summary text",
        "confidence": 0.8,
        "limitations": [],
        "source_inputs": [discussion_id],
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "model": "test-model",
    }
    kwargs.update(overrides)
    return DiscussionEvidence(**kwargs)


def test_get_discussion_evidence_returns_empty_when_absent(db_path: Path) -> None:
    assert SqliteDiscussionEvidenceStore(db_path).get_discussion_evidence("repo-1") == []


def test_save_and_get_discussion_evidence_roundtrips(db_path: Path) -> None:
    store = SqliteDiscussionEvidenceStore(db_path)
    evidence = _make_evidence("d-1", 1)

    store.save_discussion_evidence("repo-1", [evidence])
    result = store.get_discussion_evidence("repo-1")

    assert result == [evidence]


def test_save_discussion_evidence_with_limitations_and_source_inputs(db_path: Path) -> None:
    store = SqliteDiscussionEvidenceStore(db_path)
    evidence = _make_evidence(
        "d-1", 1, limitations=["low confidence"], source_inputs=["d-1", "extra-context"]
    )

    store.save_discussion_evidence("repo-1", [evidence])
    result = store.get_discussion_evidence("repo-1")

    assert result == [evidence]


def test_save_discussion_evidence_upserts_same_discussion(db_path: Path) -> None:
    store = SqliteDiscussionEvidenceStore(db_path)
    store.save_discussion_evidence("repo-1", [_make_evidence("d-1", 1, summary="first")])

    store.save_discussion_evidence("repo-1", [_make_evidence("d-1", 1, summary="second")])
    result = store.get_discussion_evidence("repo-1")

    assert len(result) == 1
    assert result[0].summary == "second"


def test_unknown_repository_id_returns_empty_list(db_path: Path) -> None:
    store = SqliteDiscussionEvidenceStore(db_path)
    store.save_discussion_evidence("repo-1", [_make_evidence("d-1", 1)])

    assert store.get_discussion_evidence("unknown-repo") == []


def test_distinct_repositories_are_independent(db_path: Path) -> None:
    store = SqliteDiscussionEvidenceStore(db_path)
    store.save_discussion_evidence("repo-1", [_make_evidence("d-1", 1)])
    store.save_discussion_evidence("repo-2", [_make_evidence("d-2", 2)])

    assert [e.discussion_id for e in store.get_discussion_evidence("repo-1")] == ["d-1"]
    assert [e.discussion_id for e in store.get_discussion_evidence("repo-2")] == ["d-2"]


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteDiscussionEvidenceStore(db_path)
    store.initialize()
    store.save_discussion_evidence("repo-1", [_make_evidence("d-1", 1)])

    assert len(store.get_discussion_evidence("repo-1")) == 1
