import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import psycopg  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.types import ASGIApp  # noqa: E402

from git_it.api.limiter import limiter  # noqa: E402
from git_it.api.routes.repos import router as repos_router  # noqa: E402

_STATIC_DIR = Path(__file__).parent.parent / "static"

_logger = logging.getLogger(__name__)


def _postgres_unavailable_handler(request: Request, exc: Exception) -> Response:
    """Fail loud when the Postgres backend selected via DATABASE_URL is unreachable.

    Never falls back to SQLite (spec 014). The message is static so the
    connection string (which may embed credentials) can never leak; the raw
    exception is logged server-side by type name only.
    """
    _logger.warning("database unavailable: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Database unavailable: the PostgreSQL backend selected via "
                "DATABASE_URL could not be reached."
            )
        },
    )


class _NoCacheStaticMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


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
    app.add_exception_handler(psycopg.OperationalError, _postgres_unavailable_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(_NoCacheStaticMiddleware)
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
