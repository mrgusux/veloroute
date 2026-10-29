"""
Client-Side Token Bucket Rate Limiting (Self-Throttling)
=========================================================
Thread-safe and async-safe token bucket rate limiters to track and enforce
RPM (Requests Per Minute) and TPM (Tokens Per Minute) client-side.
Auto-throttles requests via async queues to completely prevent provider 429s.
"""
from __future__ import annotations
import asyncio
import time
import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TokenBucket:
    """A thread-safe Token Bucket for managing rate limits (RPM or TPM)."""

    def __init__(self, limit: float, window: float = 60.0):
        self.limit = limit
        self.window = window
        self.tokens = limit
        self.last_update = time.time()
        self.lock = threading.Lock()

    def _replenish(self):
        now = time.time()
        elapsed = now - self.last_update
        self.last_update = now
        added = elapsed * (self.limit / self.window)
        self.tokens = min(self.limit, self.tokens + added)

    def get_wait_time(self, tokens_needed: float) -> float:
        """
        Check and (only on success) deduct tokens.

        Returns 0.0 when the request is admitted.  Otherwise returns the
        number of seconds the caller must wait before retrying.  Tokens are
        never driven negative: a rejected request must not create unbounded
        debt for every subsequent caller.
        """
        # A single request larger than the whole window can never be admitted
        # by waiting; clamp it so the limiter degrades to "one window per
        # request" instead of deadlocking forever.
        if self.limit <= 0:
            return 0.0
        tokens_needed = min(float(tokens_needed), float(self.limit))

        with self.lock:
            self._replenish()
            if self.tokens >= tokens_needed:
                self.tokens -= tokens_needed
                return 0.0

            deficit = tokens_needed - self.tokens
            fill_rate = self.limit / self.window
            return deficit / fill_rate if fill_rate > 0 else self.window


class RateLimiter:
    """Enforces RPM and TPM rate limits together on a single endpoint/model."""

    def __init__(self, rpm_limit: Optional[int] = None, tpm_limit: Optional[int] = None):
        self.rpm_bucket = TokenBucket(rpm_limit) if rpm_limit else None
        self.tpm_bucket = TokenBucket(tpm_limit) if tpm_limit else None

    async def acquire(self, tokens: int = 1):
        """
        Acquire rate limiting capacity, sleeping and RE-CHECKING until both
        buckets admit the request.  (The previous implementation slept once
        and proceeded even when the request was still over budget.)
        """
        tokens = max(1, int(tokens or 1))
        rpm_reserved = self.rpm_bucket is None
        tpm_reserved = self.tpm_bucket is None

        while True:
            wait_rpm = 0.0
            wait_tpm = 0.0

            if not rpm_reserved and self.rpm_bucket:
                wait_rpm = self.rpm_bucket.get_wait_time(1)
                if wait_rpm <= 0.0:
                    rpm_reserved = True

            if not tpm_reserved and self.tpm_bucket:
                wait_tpm = self.tpm_bucket.get_wait_time(tokens)
                if wait_tpm <= 0.0:
                    tpm_reserved = True

            if rpm_reserved and tpm_reserved:
                return

            max_wait = max(wait_rpm, wait_tpm, 0.01)
            # Cap individual sleeps so cancellation remains responsive.
            await asyncio.sleep(min(max_wait, 60.0))


class RateLimitManager:
    """Global manager for rate limiters by model and key."""

    def __init__(self, limits: Optional[Dict[str, Dict[str, int]]] = None):
        self.limits = limits or {}
        self._limiters: Dict[str, RateLimiter] = {}
        self._lock = threading.Lock()

    def get_limiter(self, model: str) -> RateLimiter:
        """Retrieve or construct the RateLimiter for a given model."""
        with self._lock:
            if model not in self._limiters:
                # 1. Exact model match
                model_limits = self.limits.get(model)
                # 2. Provider match if model is "provider/model"
                if not model_limits and "/" in model:
                    prov = model.split("/")[0]
                    model_limits = self.limits.get(prov)
                # 3. Fallback to default
                if not model_limits:
                    model_limits = self.limits.get("default", {})

                rpm = model_limits.get("rpm")
                tpm = model_limits.get("tpm")
                self._limiters[model] = RateLimiter(rpm, tpm)
            return self._limiters[model]
