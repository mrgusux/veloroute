import os
import secrets
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from .deps import SESSION_TOKEN
from .models import TokenResponse

router = APIRouter()

@router.post("/api/v1/token", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    correct_user = os.environ.get("LLMCYCLE_USER_ADMIN", "admin")
    correct_pass = os.environ.get("LLMCYCLE_USER_ADMIN_PASSWORD")
    if correct_pass is None:
        # Accept the misspelled name used by earlier LLMCycle releases.
        correct_pass = os.environ.get("LLMCYCLE_USER_ADMIN_PAASWORD", "admin")
    if not (
        secrets.compare_digest(form_data.username, correct_user) and
        secrets.compare_digest(form_data.password, correct_pass)
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials",
                            headers={"WWW-Authenticate": "Bearer"})
    return TokenResponse(access_token=SESSION_TOKEN, token_type="bearer")
