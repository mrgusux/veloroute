import os
import secrets
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from veloroute import VeloRoute
from veloroute.storage import StorageManager, StorageBackend

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")
SESSION_TOKEN = secrets.token_urlsafe(32)
VIEWER_TOKEN = secrets.token_urlsafe(32)

_VIEWER_SAFE_POST_PATHS = {
    "/api/v1/guardrails/test",
    "/api/v1/cache/test",
    "/api/v1/transforms/test",
    "/api/v1/prompts/analyze",
}

# If no storage backend is configured in the environment, default to local SQLite for dashboard persistence!
storage_backend = os.environ.get("VELOROUTE_STORAGE_BACKEND")
storage_url = os.environ.get("VELOROUTE_STORAGE_URL")

if not storage_backend and not storage_url:
    storage_backend = "sqlite"
    storage_url = "sqlite+aiosqlite:///./veloroute.db"
    os.environ["VELOROUTE_STORAGE_BACKEND"] = storage_backend
    os.environ["VELOROUTE_STORAGE_URL"] = storage_url

storage = StorageManager(
    backend=storage_backend,
    url=storage_url
)

# Initialize gateway with storage and semantic cache active out of the box
llm_client = VeloRoute(storage=storage, semantic_cache=True)

async def auth(request: Request, token: str = Depends(oauth2_scheme)):
    if secrets.compare_digest(token, SESSION_TOKEN):
        return token
    if secrets.compare_digest(token, VIEWER_TOKEN):
        if request.method in ("GET", "HEAD", "OPTIONS") or request.url.path in _VIEWER_SAFE_POST_PATHS:
            return token
        raise HTTPException(
            status_code=403,
            detail="Read-only Viewer role cannot modify gateway configuration.",
        )
    raise HTTPException(status_code=401, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"})
