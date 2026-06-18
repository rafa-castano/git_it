import os
import secrets

from fastapi import Header, HTTPException


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency that enforces bearer-token auth when GIT_IT_API_KEY is set.

    If the environment variable is not set, auth is skipped (development mode).
    """
    key = os.environ.get("GIT_IT_API_KEY")
    if not key:
        return  # auth disabled
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    provided = authorization.removeprefix("Bearer ")
    if not secrets.compare_digest(provided, key):
        raise HTTPException(status_code=403, detail="Forbidden")
