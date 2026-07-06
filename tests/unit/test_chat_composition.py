"""Spec 023 (batch 123) -- `build_chat_service` wires `include_semantic_search`
from the same single source of truth as every other RAG call site:
`build_embedding_client() is not None` (gated on `OPENAI_API_KEY`)."""

from pathlib import Path

import pytest

from git_it.chat.composition import build_chat_service


def test_build_chat_service_enables_semantic_search_when_openai_api_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key")

    service = build_chat_service(tmp_path)

    assert "search_similar_commits" in service._tools


def test_build_chat_service_disables_semantic_search_when_openai_api_key_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    service = build_chat_service(tmp_path)

    assert "search_similar_commits" not in service._tools
