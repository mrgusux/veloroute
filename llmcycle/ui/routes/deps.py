import os
import secrets
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from llmcycle import LLMCycle
from llmcycle.storage import StorageManager, StorageBackend

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")
SESSION_TOKEN = secrets.token_urlsafe(32)

# If no storage backend is configured in the environment, default to local SQLite for dashboard persistence!
storage_backend = os.environ.get("LLMCYCLE_STORAGE_BACKEND")
storage_url = os.environ.get("LLMCYCLE_STORAGE_URL")

if not storage_backend and not storage_url:
    storage_backend = "sqlite"
    storage_url = "sqlite+aiosqlite:///./llmcycle.db"
    os.environ["LLMCYCLE_STORAGE_BACKEND"] = storage_backend
    os.environ["LLMCYCLE_STORAGE_URL"] = storage_url

storage = StorageManager(
    backend=storage_backend,
    url=storage_url
)

llm_client = LLMCycle(storage=storage)

async def auth(token: str = Depends(oauth2_scheme)):
    if not secrets.compare_digest(token, SESSION_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"})
    return token
