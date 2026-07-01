import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from git_it.chat.service import ChatService


def get_project_root(request: Request) -> Path:
    """Return the project root, preferring app.state over env var over cwd."""
    if hasattr(request.app.state, "project_root"):
        return request.app.state.project_root  # type: ignore[no-any-return]
    data_dir = os.environ.get("GIT_IT_DATA_DIR")
    return Path(data_dir) if data_dir else Path.cwd()


def get_chat_service(
    project_root: Annotated[Path, Depends(get_project_root)],
) -> ChatService:
    """Build the production GitItGPT chat service (litellm-backed). Tests override
    this dependency with a service wrapping a scripted fake LLM."""
    from git_it.chat.composition import build_chat_service

    return build_chat_service(project_root)
