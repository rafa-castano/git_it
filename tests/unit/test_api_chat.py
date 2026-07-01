"""Spec 012 AC-5 — POST /api/repos/{repository_id}/chat.

The endpoint runs the GitItGPT ChatService for the open repository. Tests inject a
scripted fake LLM via the `get_chat_service` dependency override, so no network is
touched. Covers: reply returned, API key required, unknown repo -> 200, and a safe
5xx when the LLM backend fails.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from git_it.chat.service import ChatService, LLMTurn, ToolCall


class _ScriptedLLM:
    def __init__(self, turns: list[LLMTurn]) -> None:
        self._turns = list(turns)

    def respond(self, *, system: str, messages: list, tools: list) -> LLMTurn:
        if self._turns:
            return self._turns.pop(0)
        return LLMTurn(text="(done)")


class _BoomLLM:
    def respond(self, *, system: str, messages: list, tools: list) -> LLMTurn:
        raise RuntimeError("sk-secret-abc123 backend exploded")


def _client_with_llm(tmp_path: Path, llm: object) -> TestClient:
    from git_it.api.app import create_app
    from git_it.api.deps import get_chat_service

    app = create_app(project_root=tmp_path)
    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        llm=llm,  # type: ignore[arg-type]
        project_root=tmp_path,
    )
    return TestClient(app)


def test_chat_returns_reply(tmp_path: Path) -> None:
    llm = _ScriptedLLM([LLMTurn(text="Tests first appear in commit feat001.")])
    client = _client_with_llm(tmp_path, llm)

    response = client.post(
        "/api/repos/repo-abc/chat",
        json={"message": "when did tests start?"},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Tests first appear in commit feat001."


def test_chat_accepts_optional_history(tmp_path: Path) -> None:
    llm = _ScriptedLLM([LLMTurn(text="ok")])
    client = _client_with_llm(tmp_path, llm)

    response = client.post(
        "/api/repos/repo-abc/chat",
        json={
            "message": "and after that?",
            "history": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "ok"


def test_chat_unknown_repo_returns_200(tmp_path: Path) -> None:
    # The model asks for a tool on a repo with no data; tools return empty, no crash.
    llm = _ScriptedLLM(
        [
            LLMTurn(tool_calls=(ToolCall(id="c1", name="search_commits", arguments={}),)),
            LLMTurn(text="I have no analyzed data for this repository."),
        ]
    )
    client = _client_with_llm(tmp_path, llm)

    response = client.post(
        "/api/repos/repo-missing/chat",
        json={"message": "what happened?"},
    )

    assert response.status_code == 200
    assert "no analyzed data" in response.json()["reply"]


def test_chat_requires_auth_when_api_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_IT_API_KEY", "secret")
    llm = _ScriptedLLM([LLMTurn(text="ok")])
    client = _client_with_llm(tmp_path, llm)

    response = client.post("/api/repos/repo-abc/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_chat_llm_failure_returns_safe_5xx(tmp_path: Path) -> None:
    client = _client_with_llm(tmp_path, _BoomLLM())

    response = client.post("/api/repos/repo-abc/chat", json={"message": "hi"})

    assert response.status_code == 503
    # The raw exception (and any secret in it) must never leak to the client.
    assert "sk-secret" not in response.text
