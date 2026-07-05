"""Tests for SqliteEmbeddingStore — embedding vector persistence (spec 023).

Mirrors test_discussion_evidence_store_sqlite.py's structure. The primary key is
(repository_id, source_type, source_id) — one extra dimension over the discussion
evidence store's (repository_id, discussion_id), so a commit_analysis row and a
discussion_evidence row sharing the same source_id string must coexist.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk
from git_it.repository_ingestion.infrastructure.sqlite import SqliteEmbeddingStore


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "embedding_store_test.sqlite3"
    SqliteEmbeddingStore(path).initialize()
    return path


def _make_chunk(source_id: str, **overrides: Any) -> EmbeddedChunk:
    kwargs: dict[str, Any] = {
        "repository_id": "repo-1",
        "source_type": "commit_analysis",
        "source_id": source_id,
        "text": "summary text",
        "vector": [0.1, 0.2, 0.3],
        "model": "text-embedding-3-small",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return EmbeddedChunk(**kwargs)


def test_get_all_embeddings_returns_empty_when_absent(db_path: Path) -> None:
    assert SqliteEmbeddingStore(db_path).get_all_embeddings("repo-1") == []


def test_save_and_get_embeddings_roundtrips(db_path: Path) -> None:
    store = SqliteEmbeddingStore(db_path)
    chunk = _make_chunk("sha-1")

    store.save_embeddings("repo-1", [chunk])
    result = store.get_all_embeddings("repo-1")

    assert result == [chunk]


def test_save_embeddings_upserts_same_repository_source_type_source_id(db_path: Path) -> None:
    store = SqliteEmbeddingStore(db_path)
    store.save_embeddings("repo-1", [_make_chunk("sha-1", text="first")])

    store.save_embeddings("repo-1", [_make_chunk("sha-1", text="second")])
    result = store.get_all_embeddings("repo-1")

    assert len(result) == 1
    assert result[0].text == "second"


def test_unknown_repository_id_returns_empty_list(db_path: Path) -> None:
    store = SqliteEmbeddingStore(db_path)
    store.save_embeddings("repo-1", [_make_chunk("sha-1")])

    assert store.get_all_embeddings("unknown-repo") == []


def test_distinct_repositories_are_independent(db_path: Path) -> None:
    store = SqliteEmbeddingStore(db_path)
    store.save_embeddings("repo-1", [_make_chunk("sha-1")])
    store.save_embeddings("repo-2", [_make_chunk("sha-2")])

    assert [c.source_id for c in store.get_all_embeddings("repo-1")] == ["sha-1"]
    assert [c.source_id for c in store.get_all_embeddings("repo-2")] == ["sha-2"]


def test_initialize_is_idempotent(db_path: Path) -> None:
    store = SqliteEmbeddingStore(db_path)
    store.initialize()
    store.save_embeddings("repo-1", [_make_chunk("sha-1")])

    assert len(store.get_all_embeddings("repo-1")) == 1


def test_distinct_source_types_with_same_source_id_coexist(db_path: Path) -> None:
    store = SqliteEmbeddingStore(db_path)
    commit_chunk = _make_chunk("42", source_type="commit_analysis", text="commit text")
    discussion_chunk = _make_chunk("42", source_type="discussion_evidence", text="discussion text")

    store.save_embeddings("repo-1", [commit_chunk, discussion_chunk])
    result = store.get_all_embeddings("repo-1")

    assert len(result) == 2
    by_source_type = {c.source_type: c for c in result}
    assert by_source_type["commit_analysis"].text == "commit text"
    assert by_source_type["discussion_evidence"].text == "discussion text"
