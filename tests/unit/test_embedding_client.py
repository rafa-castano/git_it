"""Batch 119 — LiteLLMEmbeddingClient (spec 023).

Mocks ``litellm.embedding`` so no real API call happens, mirroring the mocking
style used in ``test_llm_infrastructure_observability.py`` (batch 117) against
this same ``infrastructure/llm.py`` module. Verifies the vector extraction,
model wiring, ``observe_llm_call`` integration with ``call_site="embedding"``,
and that failures (raised exceptions, malformed responses) propagate
unchanged rather than being swallowed here -- that is ``EmbeddingService``'s
job (batch 120), not this class's.
"""

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from git_it.repository_ingestion.infrastructure.llm import EMBEDDING_MODEL, LiteLLMEmbeddingClient


def _observability_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "git_it.observability"]


def _install_fake_litellm_embedding(
    monkeypatch: pytest.MonkeyPatch, vector: list[float]
) -> dict[str, Any]:
    import litellm

    captured_kwargs: dict[str, Any] = {}

    def _fake_embedding(**kwargs: Any) -> SimpleNamespace:
        captured_kwargs.update(kwargs)
        return SimpleNamespace(data=[{"embedding": vector}])

    monkeypatch.setattr(litellm, "embedding", _fake_embedding)
    return captured_kwargs


def test_embed_returns_vector_from_mocked_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_litellm_embedding(monkeypatch, [0.1, 0.2, 0.3])

    client = LiteLLMEmbeddingClient(model="fake-embedding-model")
    result = client.embed("some text")

    assert result == [0.1, 0.2, 0.3]


def test_embed_calls_litellm_with_configured_model_and_text_as_input_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs = _install_fake_litellm_embedding(monkeypatch, [1.0])

    client = LiteLLMEmbeddingClient(model="fake-embedding-model")
    client.embed("hello world")

    assert captured_kwargs["model"] == "fake-embedding-model"
    assert captured_kwargs["input"] == ["hello world"]


def test_default_model_is_embedding_model_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs = _install_fake_litellm_embedding(monkeypatch, [1.0])

    client = LiteLLMEmbeddingClient()
    client.embed("text")

    assert client._model == EMBEDDING_MODEL
    assert captured_kwargs["model"] == EMBEDDING_MODEL


def test_constructor_model_override_is_stored_as_private_model_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_litellm_embedding(monkeypatch, [1.0])

    client = LiteLLMEmbeddingClient(model="custom-model")

    assert client._model == "custom-model"


def test_embed_observed_with_embedding_call_site(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    _install_fake_litellm_embedding(monkeypatch, [0.5])

    client = LiteLLMEmbeddingClient(model="fake-embedding-model")
    client.embed("text")

    records = _observability_records(caplog)
    assert len(records) == 1
    assert records[0].call_site == "embedding"  # type: ignore[attr-defined]
    assert records[0].model == "fake-embedding-model"  # type: ignore[attr-defined]
    assert records[0].success is True  # type: ignore[attr-defined]


def test_embed_propagates_exception_from_litellm_and_records_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="git_it.observability")
    import litellm

    class _RateLimitError(Exception):
        pass

    def _raise_rate_limit(**kwargs: Any) -> SimpleNamespace:
        raise _RateLimitError("rate limited")

    monkeypatch.setattr(litellm, "embedding", _raise_rate_limit)

    client = LiteLLMEmbeddingClient(model="fake-embedding-model")

    with pytest.raises(_RateLimitError):
        client.embed("text")

    records = _observability_records(caplog)
    assert len(records) == 1
    assert records[0].success is False  # type: ignore[attr-defined]
    assert records[0].error_type == "_RateLimitError"  # type: ignore[attr-defined]


def test_embed_raises_naturally_on_malformed_response_missing_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm

    def _fake_embedding(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace()  # no `.data` attribute at all

    monkeypatch.setattr(litellm, "embedding", _fake_embedding)

    client = LiteLLMEmbeddingClient(model="fake-embedding-model")

    with pytest.raises(AttributeError):
        client.embed("text")


def test_embed_raises_naturally_on_malformed_response_empty_data_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm

    def _fake_embedding(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(data=[])  # empty list -- no [0] to index

    monkeypatch.setattr(litellm, "embedding", _fake_embedding)

    client = LiteLLMEmbeddingClient(model="fake-embedding-model")

    with pytest.raises(IndexError):
        client.embed("text")
