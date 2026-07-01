"""Composition root for GitItGPT chat (spec 012).

Wires the production `ChatService` with the real litellm-backed LLM client. Kept
apart from the service and the adapter so the API layer depends on one builder and
tests inject a fake `ChatService` instead.
"""

from pathlib import Path

from git_it.chat.litellm_client import LiteLLMChatClient
from git_it.chat.service import ChatService
from git_it.repository_ingestion.infrastructure.llm import DEFAULT_MODEL


def build_chat_service(
    project_root: Path, *, model: str = DEFAULT_MODEL, turn_cap: int = 6
) -> ChatService:
    return ChatService(
        llm=LiteLLMChatClient(model=model),
        project_root=project_root,
        turn_cap=turn_cap,
    )
