"""Admin API endpoints for Webhook management."""
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from .deps import auth
from veloroute.core.webhooks import WebhookDispatcher, get_webhook_dispatcher

router = APIRouter()


class WebhookConfigRequest(BaseModel):
    url: Optional[str] = ""
    secret: Optional[str] = None


class TestWebhookRequest(BaseModel):
    url: Optional[str] = None
    event: Optional[str] = None
    event_type: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


def _normalize_webhook_history(items):
    out = []
    for h in items:
        rec = dict(h)
        rec.setdefault("event_type", rec.get("event", "test.ping"))
        rec.setdefault("target_url", rec.get("url", "dry-run"))
        rec.setdefault("status_code", rec.get("response_code", 200 if rec.get("status") in ("delivered", "dry_run", "dry_run_ok") else None))
        rec.setdefault("delivered", rec.get("status") in ("delivered", "dry_run", "dry_run_ok"))
        out.append(rec)
    return out


@router.get("/api/v1/webhooks/status")
async def get_webhook_status(_: str = Depends(auth)):
    dispatcher = get_webhook_dispatcher()
    return {
        "configured": dispatcher.is_configured(),
        "url": dispatcher.url,
        "webhook_url": dispatcher.url or "",
        "has_secret": bool(dispatcher.secret),
        "history": _normalize_webhook_history(dispatcher.get_history()),
    }


@router.post("/api/v1/webhooks/config")
async def set_webhook_config(req: WebhookConfigRequest, _: str = Depends(auth)):
    dispatcher = get_webhook_dispatcher()
    try:
        state = dispatcher.configure(url=req.url, secret=req.secret)
        return {"status": "ok", **state, "webhook_url": state.get("url") or ""}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/v1/webhooks/history")
async def get_webhook_history(_: str = Depends(auth)):
    dispatcher = get_webhook_dispatcher()
    return {"history": _normalize_webhook_history(dispatcher.get_history())}


@router.post("/api/v1/webhooks/history/clear")
async def clear_webhook_history(_: str = Depends(auth)):
    dispatcher = get_webhook_dispatcher()
    cleared = dispatcher.clear_history()
    return {"status": "ok", "cleared": cleared}


@router.post("/api/v1/webhooks/test")
async def test_webhook(req: TestWebhookRequest, _: str = Depends(auth)):
    dispatcher = get_webhook_dispatcher()
    custom_url = None
    if req.url and req.url.strip():
        try:
            custom_url = WebhookDispatcher.validate_webhook_url(req.url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    evt_name = (req.event_type or req.event or "test.ping").strip()
    test_data = req.data or {
        "message": "This is a test notification from VeloRoute Gateway",
        "service": "veloroute",
    }
    effective_url = custom_url or (dispatcher.url or "").strip()
    if effective_url:
        await dispatcher.dispatch(evt_name, test_data, target_url=effective_url)
        return {
            "status": "ok",
            "dispatched": True,
            "dry_run": False,
            "url": effective_url,
            "message": "Test webhook scheduled for delivery",
        }

    # Record dry-run diagnostic event when no URL is configured so UI shows immediate feedback
    dispatcher._record_history({
        "id": f"evt_{int(time.time()*1000)}",
        "event": evt_name,
        "event_type": evt_name,
        "url": "(local dry-run — configure URL to send HTTP POST)",
        "target_url": "(local dry-run)",
        "timestamp": time.time(),
        "status": "dry_run_ok",
        "delivered": True,
        "attempts": 1,
        "response_code": 200,
        "status_code": 200,
    })
    return {
        "status": "ok",
        "dispatched": False,
        "dry_run": True,
        "message": "Test webhook recorded in dry-run mode (configure a Webhook URL for live HTTP delivery)",
    }
