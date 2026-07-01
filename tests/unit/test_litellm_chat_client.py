"""Spec 012 — LiteLLMChatClient bridges the internal ChatLLM contract to litellm.

The client translates our internal messages/tool-schemas into litellm's
OpenAI-style wire format, calls `litellm.completion`, and maps the response back
into an `LLMTurn`. Tests monkeypatch `litellm.completion` to a canned response —
no network, fully deterministic.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from git_it.chat.litellm_client import LiteLLMChatClient
from git_it.chat.service import LLMTurn, StreamPart


def _install_fake_completion(
    monkeypatch: pytest.MonkeyPatch, message: SimpleNamespace
) -> dict[str, Any]:
    """Patch litellm.completion to return `message` and capture its kwargs."""
    import litellm

    captured: dict[str, Any] = {}

    def _fake_completion(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(litellm, "completion", _fake_completion)
    return captured


def test_maps_text_response_to_final_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    message = SimpleNamespace(content="Here is the answer.", tool_calls=None)
    _install_fake_completion(monkeypatch, message)

    client = LiteLLMChatClient()
    turn = client.respond(system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])

    assert isinstance(turn, LLMTurn)
    assert turn.text == "Here is the answer."
    assert turn.tool_calls == ()


def test_maps_tool_call_response(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="search_commits", arguments='{"category": "feature"}'),
    )
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    _install_fake_completion(monkeypatch, message)

    client = LiteLLMChatClient()
    turn = client.respond(system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])

    assert len(turn.tool_calls) == 1
    call = turn.tool_calls[0]
    assert call.id == "call_1"
    assert call.name == "search_commits"
    assert call.arguments == {"category": "feature"}


def test_translates_messages_and_tools_to_litellm_wire_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = SimpleNamespace(content="ok", tool_calls=None)
    captured = _install_fake_completion(monkeypatch, message)

    client = LiteLLMChatClient()
    internal_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "search_commits", "arguments": {"limit": 5}}],
        },
        {"role": "tool", "tool_call_id": "c1", "name": "search_commits", "content": "{}"},
    ]
    tools = [
        {
            "name": "search_commits",
            "description": "Search commits.",
            "parameters": {"category": "string (optional)"},
        }
    ]
    client.respond(system="SYSTEM RULES", messages=internal_messages, tools=tools)

    sent = captured["messages"]
    # First message is the system prompt.
    assert sent[0] == {"role": "system", "content": "SYSTEM RULES"}
    # The assistant tool call is in OpenAI function-call shape.
    assistant = next(m for m in sent if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["type"] == "function"
    assert assistant["tool_calls"][0]["function"]["name"] == "search_commits"
    # The tool result carries its tool_call_id.
    tool_msg = next(m for m in sent if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "c1"
    # Tools are advertised as OpenAI function tools.
    sent_tools = captured["tools"]
    assert sent_tools[0]["type"] == "function"
    assert sent_tools[0]["function"]["name"] == "search_commits"


# ---------------------------------------------------------------------------
# Spec 013 AC-1 — LiteLLMChatClient.respond_stream
# ---------------------------------------------------------------------------


def _delta(content: str | None = None, tool_calls: list[Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _chunk(delta: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _install_fake_stream(
    monkeypatch: pytest.MonkeyPatch, chunks: list[SimpleNamespace]
) -> dict[str, Any]:
    """Patch litellm.completion(stream=True) to yield `chunks`, capturing kwargs."""
    import litellm

    captured: dict[str, Any] = {}

    def _fake_completion(**kwargs: Any) -> list[SimpleNamespace]:
        captured.update(kwargs)
        return chunks

    monkeypatch.setattr(litellm, "completion", _fake_completion)
    return captured


def test_respond_stream_yields_text_deltas_then_final_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [_chunk(_delta(content="Hello")), _chunk(_delta(content=" world"))]
    _install_fake_stream(monkeypatch, chunks)

    client = LiteLLMChatClient()
    parts = list(
        client.respond_stream(system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])
    )

    assert [p.text_delta for p in parts if p.text_delta] == ["Hello", " world"]
    final = parts[-1]
    assert isinstance(final, StreamPart)
    assert final.turn is not None
    assert final.turn.text == "Hello world"
    assert final.turn.tool_calls == ()


def test_respond_stream_assembles_tool_call_from_deltas_no_text_leaked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_call_delta_1 = SimpleNamespace(
        index=0, id="call_1", function=SimpleNamespace(name="search_commits", arguments='{"cat')
    )
    tool_call_delta_2 = SimpleNamespace(
        index=0, id=None, function=SimpleNamespace(name=None, arguments='egory": "feature"}')
    )
    chunks = [
        _chunk(_delta(tool_calls=[tool_call_delta_1])),
        _chunk(_delta(tool_calls=[tool_call_delta_2])),
    ]
    _install_fake_stream(monkeypatch, chunks)

    client = LiteLLMChatClient()
    parts = list(
        client.respond_stream(system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])
    )

    # Contract: a tool-calling turn must never leak a text delta.
    assert all(p.text_delta is None for p in parts)
    final = parts[-1].turn
    assert final is not None
    assert len(final.tool_calls) == 1
    call = final.tool_calls[0]
    assert call.id == "call_1"
    assert call.name == "search_commits"
    assert call.arguments == {"category": "feature"}


def test_respond_stream_passes_stream_true_to_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_stream(monkeypatch, [_chunk(_delta(content="ok"))])

    client = LiteLLMChatClient()
    list(
        client.respond_stream(system="sys", messages=[{"role": "user", "content": "hi"}], tools=[])
    )

    assert captured["stream"] is True
