"""
Webhook Notification Dispatcher
===============================
Provides background asynchronous webhook delivery with HMAC-SHA256 signatures
and retry logic for critical gateway events (circuit trips, budget alerts, key revocation).
Inspired by Portkey Gateway, LiteLLM, and Bifrost.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("veloroute.webhooks")


@dataclass
class WebhookEvent:
    event: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: f"evt_{int(time.time()*1000)}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.event_id,
            "event": self.event,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class WebhookDispatcher:
    """Dispatches webhook notifications asynchronously with HMAC signatures."""

    def __init__(
        self,
        url: Optional[str] = None,
        secret: Optional[str] = None,
        timeout: float = 5.0,
        max_retries: int = 3,
    ):
        self.url = url or os.environ.get("VELOROUTE_WEBHOOK_URL")
        self.secret = secret or os.environ.get("VELOROUTE_WEBHOOK_SECRET")
        self.timeout = timeout
        self.max_retries = max_retries
        self._history: List[Dict[str, Any]] = []
        self._max_history = 50

    def is_configured(self) -> bool:
        return bool(self.url and self.url.strip())

    @staticmethod
    def validate_webhook_url(url: Optional[str]) -> str:
        """Validate webhook URL scheme and block cloud metadata and SSRF targets."""
        if not url or not str(url).strip():
            return ""
        from veloroute.utils import validate_url_ssrf
        return validate_url_ssrf(url)

    def configure(self, url: Optional[str] = None, secret: Optional[str] = None) -> Dict[str, Any]:
        """Update webhook URL and HMAC secret at runtime."""
        if url is not None:
            self.url = self.validate_webhook_url(url) if url.strip() else None
        if secret is not None:
            self.secret = secret.strip() if secret.strip() else None
        return {
            "configured": self.is_configured(),
            "url": self.url,
            "has_secret": bool(self.secret),
        }

    def _sign(self, payload_bytes: bytes) -> str:
        if not self.secret:
            return ""
        return hmac.new(
            self.secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()

    async def dispatch(self, event: str, data: Dict[str, Any], target_url: Optional[str] = None) -> None:
        """Trigger an event; schedules fire-and-forget delivery task."""
        raw_url = (target_url or "").strip() or (self.url or "").strip()
        if not raw_url:
            return
        try:
            effective_url = self.validate_webhook_url(raw_url)
        except Exception as e:
            logger.warning(f"Webhook dispatch cancelled: invalid or unsafe URL '{raw_url}': {e}")
            return
        evt = WebhookEvent(event=event, data=data)
        asyncio.create_task(self._deliver(evt, target_url=effective_url))

    async def _deliver(self, evt: WebhookEvent, target_url: Optional[str] = None) -> bool:
        effective_url = (target_url or "").strip() or (self.url or "").strip()
        if not effective_url:
            return False
        payload = evt.to_dict()
        payload_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "VeloRoute-Webhook/1.0",
            "X-VeloRoute-Event": evt.event,
            "X-VeloRoute-Event-Id": evt.event_id,
        }
        sig = self._sign(payload_bytes)
        if sig:
            headers["X-VeloRoute-Signature"] = sig

        record = {
            "id": evt.event_id,
            "event": evt.event,
            "url": effective_url,
            "timestamp": evt.timestamp,
            "status": "pending",
            "attempts": 0,
            "response_code": None,
        }

        success = False
        for attempt in range(1, self.max_retries + 1):
            record["attempts"] = attempt
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(effective_url, content=payload_bytes, headers=headers)
                    record["response_code"] = resp.status_code
                    if resp.is_success:
                        record["status"] = "delivered"
                        success = True
                        break
                    else:
                        logger.warning(
                            f"Webhook {evt.event} attempt {attempt} failed with status {resp.status_code}"
                        )
            except Exception as e:
                logger.warning(f"Webhook {evt.event} attempt {attempt} error: {e}")
                record["error"] = str(e)

            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

        if not success:
            record["status"] = "failed"

        self._record_history(record)
        return success

    def _record_history(self, record: Dict[str, Any]) -> None:
        self._history.insert(0, record)
        if len(self._history) > self._max_history:
            self._history.pop()

    def clear_history(self) -> int:
        count = len(self._history)
        self._history.clear()
        return count

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._history)


_default_dispatcher: Optional[WebhookDispatcher] = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    global _default_dispatcher
    if _default_dispatcher is None:
        _default_dispatcher = WebhookDispatcher()
    return _default_dispatcher
