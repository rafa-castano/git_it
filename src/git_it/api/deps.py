import os
from pathlib import Path

from fastapi import Request


def get_project_root(request: Request) -> Path:
    """Return the project root, preferring app.state over env var over cwd."""
    if hasattr(request.app.state, "project_root"):
        return request.app.state.project_root  # type: ignore[no-any-return]
    data_dir = os.environ.get("GIT_IT_DATA_DIR")
    return Path(data_dir) if data_dir else Path.cwd()
