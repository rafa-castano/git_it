"""Spec 023 (batch 123) -- `search_similar_commits` chat tool.

Mirrors `tests/unit/test_tools_registry.py`'s self-contained style: the
registry function builds its own `SemanticSearchService` internally from
`project_root`, exactly like every other tool function, so these tests
monkeypatch the composition-layer factories (`build_embedding_client`,
`build_embedding_store`) rather than injecting dependencies via a
constructor.
"""

from pathlib import Path

from git_it.api.schemas import SimilaritySearchResponse
from git_it.repository_ingestion.application.semantic_search_service import SimilarityResult


class _StubEmbeddingClient:
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class _StubEmbeddingReader:
    def __init__(self, chunks: list[SimilarityResult]) -> None:
        self._chunks = chunks

    def get_all_embeddings(self, repository_id: str) -> list[object]:
        # Not used directly -- SemanticSearchService is monkeypatched at the
        # service level in most tests below, so this stub is unused there.
        raise NotImplementedError


def test_search_similar_commits_returns_ranked_results(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from git_it.tools import registry

    scripted = [
        SimilarityResult(
            source_type="commit_analysis",
            evidence_ref="abc123",
            summary_text="Fixed a SQL injection vulnerability.",
            score=0.92,
        ),
        SimilarityResult(
            source_type="discussion_evidence",
            evidence_ref="https://github.com/acme/repo/discussions/7",
            summary_text="Discussed flaky test suite mitigation.",
            score=0.81,
        ),
    ]

    class _StubService:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def search(self, repository_id: str, query: str, top_k: int = 10) -> list[SimilarityResult]:
            assert repository_id == "repo-abc"
            assert query == "security mistakes"
            return scripted

    monkeypatch.setattr(registry, "build_embedding_client", lambda: _StubEmbeddingClient())
    monkeypatch.setattr(registry, "build_embedding_store", lambda *, project_root: object())
    monkeypatch.setattr(registry, "SemanticSearchService", _StubService)

    result = registry.search_similar_commits(tmp_path, "repo-abc", query="security mistakes")

    assert isinstance(result, SimilaritySearchResponse)
    assert len(result.results) == 2
    assert result.results[0].source_type == "commit_analysis"
    assert result.results[0].evidence_ref == "abc123"
    assert result.results[0].summary_text == "Fixed a SQL injection vulnerability."
    assert result.results[0].score == 0.92


def test_search_similar_commits_returns_empty_when_embedding_client_unavailable(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    from git_it.tools import registry

    monkeypatch.setattr(registry, "build_embedding_client", lambda: None)

    result = registry.search_similar_commits(tmp_path, "repo-abc", query="anything")

    assert isinstance(result, SimilaritySearchResponse)
    assert result.results == []


def test_search_similar_commits_returns_empty_for_blank_query(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    from git_it.tools import registry

    class _RaisingService:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def search(self, repository_id: str, query: str, top_k: int = 10) -> list[SimilarityResult]:
            raise ValueError("query must not be empty")

    monkeypatch.setattr(registry, "build_embedding_client", lambda: _StubEmbeddingClient())
    monkeypatch.setattr(registry, "build_embedding_store", lambda *, project_root: object())
    monkeypatch.setattr(registry, "SemanticSearchService", _RaisingService)

    result = registry.search_similar_commits(tmp_path, "repo-abc", query="   ")

    assert isinstance(result, SimilaritySearchResponse)
    assert result.results == []
