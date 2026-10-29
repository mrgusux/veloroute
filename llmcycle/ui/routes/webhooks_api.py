"""Admin API endpoints for Webhook management."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any

from .deps import auth
from llmcycle.core.webhooks import get_webhook_dispatcher

router = APIRouter()


class TestWebhookRequest(BaseModel):
    url: Optional[str] = None
    event: Optional[str] = "test.ping"
    data: Optional[Dict[str, Any]] = None


@router.get("/api/v1/webhooks/status")
async def get_webhook_status(_: str = Depends(auth)):
    dispatcher = get_webhook_dispatcher()
    return {
        "configured": dispatcher.is_configured(),
        "url": dispatcher.url,
        "has_secret": bool(dispatcher.secret),
    }


@router.get("/api/v1/webhooks/history")
async def get_webhook_history(_: str = Depends(auth)):
    dispatcher = get_webhook_dispatcher()
    return {"history": dispatcher.get_history()}


@router.post("/api/v1/webhooks/test")
async def test_webhook(req: TestWebhookRequest, _: str = Depends(auth)):
    dispatcher = get_webhook_dispatcher()
    test_data = req.data or {
        "message": "This is a test notification from LLMCycle Gateway",
        "service": "llmcycle",
    }
    await dispatcher.dispatch(req.event or "test.ping", test_data)
    return {"status": "ok", "message": "Test webhook scheduled for delivery"}
