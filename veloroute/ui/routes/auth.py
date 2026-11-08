import os
import secrets
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from .deps import SESSION_TOKEN, VIEWER_TOKEN, auth
from .models import TokenResponse

router = APIRouter()

@router.post("/api/v1/token", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    admin_user = os.environ.get("VELOROUTE_USER_ADMIN", "admin")
    admin_pass = os.environ.get("VELOROUTE_USER_ADMIN_PASSWORD", "admin")
    if (
        secrets.compare_digest(form_data.username, admin_user)
        and secrets.compare_digest(form_data.password, admin_pass)
    ):
        return TokenResponse(access_token=SESSION_TOKEN, token_type="bearer", role="admin")

    viewer_user = os.environ.get("VELOROUTE_USER_VIEWER", "viewer")
    viewer_pass = os.environ.get("VELOROUTE_USER_VIEWER_PASSWORD", "viewer")
    if (
        viewer_user
        and secrets.compare_digest(form_data.username, viewer_user)
        and secrets.compare_digest(form_data.password, viewer_pass)
    ):
        return TokenResponse(access_token=VIEWER_TOKEN, token_type="bearer", role="viewer")

    raise HTTPException(
        status_code=401,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/api/v1/me")
async def get_current_session(token: str = Depends(auth)):
    role = "viewer" if secrets.compare_digest(token, VIEWER_TOKEN) else "admin"
    return {"role": role, "read_only": role == "viewer"}
