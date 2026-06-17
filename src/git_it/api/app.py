from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from git_it.api.routes.repos import router as repos_router


def create_app(project_root: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        project_root: Optional path override for the data directory.  When
            ``None`` the app reads :envvar:`GIT_IT_DATA_DIR` at request time
            (see :mod:`git_it.api.deps`).
    """
    app = FastAPI(title="Git It API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(repos_router)

    if project_root is not None:
        app.state.project_root = project_root

    return app


# Module-level app instance — used by `uvicorn git_it.api.app:app`
# and by `git-it serve`.  Reads GIT_IT_DATA_DIR at request time.
app = create_app()
