from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402

from git_it.api.limiter import limiter  # noqa: E402
from git_it.api.routes.repos import router as repos_router  # noqa: E402

_STATIC_DIR = Path(__file__).parent.parent / "static"


def create_app(project_root: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        project_root: Optional path override for the data directory.  When
            ``None`` the app reads :envvar:`GIT_IT_DATA_DIR` at request time
            (see :mod:`git_it.api.deps`).
    """
    app = FastAPI(title="Git It API", version="0.1.0")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(repos_router)

    if project_root is not None:
        app.state.project_root = project_root

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/static/index.html")

    return app


# Module-level app instance — used by `uvicorn git_it.api.app:app`
# and by `git-it serve`.  Reads GIT_IT_DATA_DIR at request time.
app = create_app()
