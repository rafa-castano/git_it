from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from git_it.repository_ingestion.application.semantic_search_service import (
    SemanticSearchService,
    SimilarityResult,
)
from git_it.repository_ingestion.domain.embeddings import EmbeddedChunk

_REPO_ID = "repo-1"


class _StubEmbeddingClient:
    """Fake EmbeddingClient returning a fixed vector for the query, tracking calls."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return self._vector


class _StubEmbeddingReader:
    """Fake EmbeddingReader returning a fixed corpus of EmbeddedChunk."""

    def __init__(self, chunks: list[EmbeddedChunk]) -> None:
        self._chunks = chunks

    def get_all_embeddings(self, repository_id: str) -> list[EmbeddedChunk]:
        return self._chunks


def _make_chunk(
    *,
    source_type: str = "commit_analysis",
    source_id: str = "sha1",
    text: str = "some summary",
    vector: list[float],
    model: str = "fake-embed-model",
) -> EmbeddedChunk:
    return EmbeddedChunk(
        repository_id=_REPO_ID,
        source_type=source_type,  # type: ignore[arg-type]
        source_id=source_id,
        text=text,
        vector=vector,
        model=model,
        created_at=datetime.now(UTC),
    )


def test_search_ranks_results_by_cosine_similarity_descending() -> None:
    parallel = _make_chunk(source_id="sha-parallel", text="parallel", vector=[1.0, 0.0])
    orthogonal = _make_chunk(source_id="sha-orthogonal", text="orthogonal", vector=[0.0, 1.0])
    opposite = _make_chunk(source_id="sha-opposite", text="opposite", vector=[-1.0, 0.0])
    reader = _StubEmbeddingReader([orthogonal, opposite, parallel])
    client = _StubEmbeddingClient([1.0, 0.0])
    service = SemanticSearchService(client, reader)

    results = service.search(_REPO_ID, "some query", top_k=10)

    assert [r.evidence_ref for r in results] == ["sha-parallel", "sha-orthogonal", "sha-opposite"]
    assert results[0].score == pytest.approx(1.0)
    assert results[1].score == pytest.approx(0.0)
    assert results[2].score == pytest.approx(-1.0)


def test_search_top_k_truncates_correctly() -> None:
    v1 = _make_chunk(source_id="v1", vector=[1.0, 0.0])
    v2 = _make_chunk(source_id="v2", vector=[1.0, 1.0])
    v3 = _make_chunk(source_id="v3", vector=[0.0, 1.0])
    v4 = _make_chunk(source_id="v4", vector=[-1.0, 1.0])
    v5 = _make_chunk(source_id="v5", vector=[-1.0, 0.0])
    reader = _StubEmbeddingReader([v5, v3, v1, v4, v2])
    client = _StubEmbeddingClient([1.0, 0.0])
    service = SemanticSearchService(client, reader)

    results = service.search(_REPO_ID, "some query", top_k=3)

    assert len(results) == 3
    assert [r.evidence_ref for r in results] == ["v1", "v2", "v3"]


def test_search_empty_corpus_returns_empty_list_without_exception() -> None:
    reader = _StubEmbeddingReader([])
    client = _StubEmbeddingClient([1.0, 0.0])
    service = SemanticSearchService(client, reader)

    results = service.search(_REPO_ID, "some query", top_k=10)

    assert results == []


@pytest.mark.parametrize("bad_query", ["", "   "])
def test_search_rejects_empty_or_whitespace_query_without_embedding(bad_query: str) -> None:
    reader = _StubEmbeddingReader([_make_chunk(vector=[1.0, 0.0])])
    client = _StubEmbeddingClient([1.0, 0.0])
    service = SemanticSearchService(client, reader)

    with pytest.raises(ValueError):
        service.search(_REPO_ID, bad_query, top_k=10)

    assert client.calls == []


def test_search_result_carries_correct_evidence_ref_for_both_source_types() -> None:
    commit_chunk = _make_chunk(
        source_type="commit_analysis",
        source_id="abc123",
        text="commit summary",
        vector=[1.0, 0.0],
    )
    discussion_chunk = _make_chunk(
        source_type="discussion_evidence",
        source_id="https://github.com/owner/repo/discussions/1",
        text="discussion summary",
        vector=[1.0, 0.0],
    )
    reader = _StubEmbeddingReader([commit_chunk, discussion_chunk])
    client = _StubEmbeddingClient([1.0, 0.0])
    service = SemanticSearchService(client, reader)

    results = service.search(_REPO_ID, "some query", top_k=10)

    by_type = {r.source_type: r for r in results}
    assert by_type["commit_analysis"].evidence_ref == "abc123"
    assert by_type["commit_analysis"].summary_text == "commit summary"
    assert (
        by_type["discussion_evidence"].evidence_ref == "https://github.com/owner/repo/discussions/1"
    )
    assert by_type["discussion_evidence"].summary_text == "discussion summary"


def test_search_zero_magnitude_stored_vector_does_not_raise_zero_division_error() -> None:
    zero_chunk = _make_chunk(source_id="zero-vector", vector=[0.0, 0.0])
    normal_chunk = _make_chunk(source_id="normal", vector=[1.0, 0.0])
    reader = _StubEmbeddingReader([zero_chunk, normal_chunk])
    client = _StubEmbeddingClient([1.0, 0.0])
    service = SemanticSearchService(client, reader)

    results = service.search(_REPO_ID, "some query", top_k=10)

    by_id = {r.evidence_ref: r for r in results}
    assert by_id["zero-vector"].score == 0.0
    assert by_id["normal"].score == pytest.approx(1.0)


def test_search_default_top_k_is_10() -> None:
    chunks = []
    for i in range(12):
        x = float(12 - i)
        y = float(i)
        chunks.append(_make_chunk(source_id=f"item-{i}", vector=[x, y]))
    reader = _StubEmbeddingReader(chunks)
    client = _StubEmbeddingClient([1.0, 0.0])
    service = SemanticSearchService(client, reader)

    results = service.search(_REPO_ID, "some query")

    assert len(results) == 10
    # Cosine similarity to [1, 0] is x / sqrt(x^2 + y^2), strictly decreasing as i increases
    # for i in 0..11 here, so the top 10 are items 0..9 in that order.
    assert [r.evidence_ref for r in results] == [f"item-{i}" for i in range(10)]
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_similarity_result_is_frozen_dataclass_with_expected_fields() -> None:
    result = SimilarityResult(
        source_type="commit_analysis",
        evidence_ref="abc123",
        summary_text="a summary",
        score=0.5,
    )

    assert result.source_type == "commit_analysis"
    assert result.evidence_ref == "abc123"
    assert result.summary_text == "a summary"
    assert result.score == 0.5
    with pytest.raises(FrozenInstanceError):
        result.score = 0.9  # type: ignore[misc]
