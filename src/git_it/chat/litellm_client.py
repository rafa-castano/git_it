"""LiteLLMChatClient — the production `ChatLLM` implementation (spec 012).

Bridges the internal, transport-neutral chat contract (`ChatLLM`, `LLMTurn`,
`ToolCall`) to litellm's OpenAI-style tool-calling wire format. Kept separate from
`ChatService` so the service stays testable with a trivial scripted fake and this
adapter is the only place that knows litellm's shape.
"""

import json
from collections.abc import Iterator
from typing import Any

from git_it.chat.service import LLMTurn, StreamPart, ToolCall
from git_it.repository_ingestion.infrastructure.llm import DEFAULT_MODEL

_DEFAULT_MAX_TOKENS = 1024


class LiteLLMChatClient:
    def __init__(
        self, *, model: str = DEFAULT_MODEL, max_tokens: int = _DEFAULT_MAX_TOKENS
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens

    def respond(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMTurn:
        import litellm

        wire_messages = [{"role": "system", "content": system}]
        wire_messages.extend(_to_wire_message(m) for m in messages)
        wire_tools = [_to_wire_tool(t) for t in tools]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": wire_messages,
            "max_tokens": self._max_tokens,
        }
        if wire_tools:
            kwargs["tools"] = wire_tools
            kwargs["tool_choice"] = "auto"

        response = litellm.completion(**kwargs)
        message = response.choices[0].message  # type: ignore[union-attr]
        return _from_wire_message(message)

    def respond_stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Iterator[StreamPart]:
        """Spec 013 AC-1: yields text deltas as they arrive; the final part
        carries the fully assembled LLMTurn. A turn commits to one mode from
        its first chunk — a tool-calling turn never yields a text delta."""
        import litellm

        wire_messages = [{"role": "system", "content": system}]
        wire_messages.extend(_to_wire_message(m) for m in messages)
        wire_tools = [_to_wire_tool(t) for t in tools]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": wire_messages,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if wire_tools:
            kwargs["tools"] = wire_tools
            kwargs["tool_choice"] = "auto"

        content_parts: list[str] = []
        tool_calls_by_index: dict[int, dict[str, Any]] = {}

        for chunk in litellm.completion(**kwargs):
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                content_parts.append(content)
                yield StreamPart(text_delta=content)
            for tc_delta in getattr(delta, "tool_calls", None) or []:
                acc = tool_calls_by_index.setdefault(
                    tc_delta.index, {"id": None, "name": None, "arguments": ""}
                )
                if tc_delta.id:
                    acc["id"] = tc_delta.id
                function = getattr(tc_delta, "function", None)
                if function is not None:
                    if getattr(function, "name", None):
                        acc["name"] = function.name
                    if getattr(function, "arguments", None):
                        acc["arguments"] += function.arguments

        text = "".join(content_parts)
        if tool_calls_by_index:
            calls = tuple(
                ToolCall(
                    id=acc["id"] or f"call_{i}",
                    name=acc["name"] or "",
                    arguments=_parse_arguments(acc["arguments"]),
                )
                for i, acc in sorted(tool_calls_by_index.items())
            )
            yield StreamPart(turn=LLMTurn(text=text or None, tool_calls=calls))
        else:
            yield StreamPart(turn=LLMTurn(text=text))


def _to_wire_message(message: dict[str, Any]) -> dict[str, Any]:
    """Translate one internal message into litellm's OpenAI-style shape."""
    role = message.get("role")
    if role == "assistant" and message.get("tool_calls"):
        return {
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {
                        "name": c["name"],
                        "arguments": json.dumps(c.get("arguments") or {}),
                    },
                }
                for c in message["tool_calls"]
            ],
        }
    if role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.get("tool_call_id"),
            "content": message.get("content") or "",
        }
    return {"role": role, "content": message.get("content") or ""}


def _to_wire_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Translate an internal tool descriptor into an OpenAI function-tool schema."""
    properties = {
        name: {"type": "string", "description": str(desc)}
        for name, desc in (tool.get("parameters") or {}).items()
    }
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": {"type": "object", "properties": properties, "required": []},
        },
    }


def _from_wire_message(message: Any) -> LLMTurn:
    """Map a litellm response message back into an internal LLMTurn."""
    tool_calls = getattr(message, "tool_calls", None)
    text = getattr(message, "content", None)
    if tool_calls:
        calls = tuple(
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=_parse_arguments(tc.function.arguments),
            )
            for tc in tool_calls
        )
        return LLMTurn(text=text, tool_calls=calls)
    return LLMTurn(text=text or "")


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
