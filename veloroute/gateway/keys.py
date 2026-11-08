"""
Virtual API Keys
================

Production gateways (LiteLLM, Portkey, One API, Bifrost …) do not expose the
upstream provider keys to callers.  They issue *virtual* keys with their own
budgets, rate limits and model scopes.  This module implements that layer for
VeloRoute.

Design notes
------------
* Only a SHA-256 hash of each key is persisted.  The plaintext key is returned
  exactly once (at creation/rotation) and is never stored.
* Enforcement is **opt-in**: it activates automatically as soon as one virtual
  key exists, or when ``VELOROUTE_REQUIRE_API_KEY=1`` is set.  Existing
  deployments therefore keep working until they create their first key.
* RPM/TPM limits use a 60-second sliding window.  Requests are reserved at
  authorization time and reconciled with real usage afterwards.
* All state is guarded by a re-entrant thread lock; persistence is delegated
  to ``StorageManager.save_config`` / ``get_config`` so SQL, Redis and Mongo
  backends all work without schema changes.
"""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PERSIST_KEY = "gateway.virtual_keys"
KEY_PREFIX = os.environ.get("VELOROUTE_KEY_PREFIX", "sk-velo-")
WINDOW_SECONDS = 60.0


class GatewayAuthError(Exception):
    """Authentication/authorization failure carrying an OpenAI-style payload."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "message": self.message,
                "type": "invalid_request_error" if self.status_code < 500 else "server_error",
                "code": self.code,
            }
        }


@dataclass
class _KeyWindow:
    requests: Deque[float] = field(default_factory=deque)
    tokens: Deque[Tuple[float, int]] = field(default_factory=deque)
    reservations: Dict[str, Tuple[float, int]] = field(default_factory=dict)

    def prune(self, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()
        while self.tokens and self.tokens[0][0] < cutoff:
            self.tokens.popleft()
        for reservation_id, (timestamp, _) in list(self.reservations.items()):
            if timestamp < cutoff:
                self.reservations.pop(reservation_id, None)

    def token_total(self) -> int:
        return sum(t for _, t in self.tokens) + sum(
            amount for _, amount in self.reservations.values()
        )


def _now() -> float:
    return time.time()


def _hash(raw_key: str, pepper: str = "") -> str:
    return hashlib.sha256((pepper + raw_key).encode("utf-8")).hexdigest()


def _display_prefix(raw_key: str) -> str:
    # Enough to identify a key in the dashboard without leaking the secret.
    return raw_key[:12] + "…" if len(raw_key) > 12 else "***"


@dataclass
class VirtualKey:
    id: str
    name: str
    key_hash: str
    key_prefix: str
    created_at: float = field(default_factory=_now)
    enabled: bool = True
    expires_at: Optional[float] = None
    budget_usd: Optional[float] = None
    spent_usd: float = 0.0
    budget_alert_threshold: Optional[float] = None  # e.g. 0.80 for 80% soft warning
    budget_alert_webhook: Optional[str] = None    # Webhook URL to notify
    auto_pause_on_budget: bool = True             # Auto-pause key when 100% budget reached
    alert_sent: bool = False                      # Tracks if warning webhook was dispatched
    rpm_limit: Optional[int] = None
    tpm_limit: Optional[int] = None
    allowed_models: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    total_requests: int = 0
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    last_used_at: Optional[float] = None
    revoked_at: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and _now() >= self.expires_at

    @property
    def is_active(self) -> bool:
        return self.enabled and self.revoked_at is None and not self.is_expired

    def to_public_dict(self) -> Dict[str, Any]:
        """Serialize without the hash (safe for API responses/dashboards)."""
        return {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "created_at": self.created_at,
            "enabled": self.enabled,
            "expires_at": self.expires_at,
            "budget_usd": self.budget_usd,
            "spent_usd": round(self.spent_usd, 8),
            "remaining_budget_usd": (
                round(max(0.0, self.budget_usd - self.spent_usd), 8)
                if self.budget_usd is not None
                else None
            ),
            "budget_alert_threshold": self.budget_alert_threshold,
            "budget_alert_webhook": self.budget_alert_webhook,
            "auto_pause_on_budget": self.auto_pause_on_budget,
            "alert_sent": self.alert_sent,
            "spent_percent": (
                round((self.spent_usd / self.budget_usd) * 100, 1)
                if self.budget_usd and self.budget_usd > 0
                else 0.0
            ),
            "rpm_limit": self.rpm_limit,
            "tpm_limit": self.tpm_limit,
            "allowed_models": list(self.allowed_models),
            "metadata": dict(self.metadata),
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "last_used_at": self.last_used_at,
            "revoked_at": self.revoked_at,
            "active": self.is_active,
        }

    def to_store_dict(self) -> Dict[str, Any]:
        d = self.to_public_dict()
        d.pop("active", None)
        d.pop("remaining_budget_usd", None)
        d["key_hash"] = self.key_hash
        return d

    @classmethod
    def from_store_dict(cls, data: Dict[str, Any]) -> "VirtualKey":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "")),
            key_hash=str(data["key_hash"]),
            key_prefix=str(data.get("key_prefix", "")),
            created_at=float(data.get("created_at") or _now()),
            enabled=bool(data.get("enabled", True)),
            expires_at=data.get("expires_at"),
            budget_usd=data.get("budget_usd"),
            spent_usd=float(data.get("spent_usd") or 0.0),
            budget_alert_threshold=data.get("budget_alert_threshold"),
            budget_alert_webhook=data.get("budget_alert_webhook"),
            auto_pause_on_budget=bool(data.get("auto_pause_on_budget", True)),
            alert_sent=bool(data.get("alert_sent", False)),
            rpm_limit=data.get("rpm_limit"),
            tpm_limit=data.get("tpm_limit"),
            allowed_models=list(data.get("allowed_models") or []),
            metadata=dict(data.get("metadata") or {}),
            total_requests=int(data.get("total_requests") or 0),
            total_tokens=int(data.get("total_tokens") or 0),
            total_prompt_tokens=int(data.get("total_prompt_tokens") or 0),
            total_completion_tokens=int(data.get("total_completion_tokens") or 0),
            last_used_at=data.get("last_used_at"),
            revoked_at=data.get("revoked_at"),
        )


class VirtualKeyManager:
    """Issues and validates virtual API keys, budgets and per-key rate limits."""

    def __init__(
        self,
        storage=None,
        *,
        enforce: Optional[bool] = None,
        persist_interval: float = 5.0,
    ):
        self.storage = storage
        self.persist_interval = max(0.0, float(persist_interval))
        env_force = os.environ.get("VELOROUTE_REQUIRE_API_KEY", "").lower() in (
            "1", "true", "yes", "on",
        )
        self._force = env_force if enforce is None else bool(enforce)
        self._pepper = os.environ.get("VELOROUTE_KEY_PEPPER", "")

        self._lock = threading.RLock()
        self._keys: Dict[str, VirtualKey] = {}
        self._by_hash: Dict[str, str] = {}          # hash -> key id
        self._windows: Dict[str, _KeyWindow] = {}
        self._queued_ms: Dict[str, int] = {}
        self._dirty = False
        self._last_saved = 0.0

    # ── properties ──────────────────────────────────────────────────────
    @property
    def enforcement_enabled(self) -> bool:
        """True when requests must present a virtual key."""
        with self._lock:
            return self._force or bool(self._keys)

    # Alias used by some callers.
    @property
    def enabled(self) -> bool:
        return self.enforcement_enabled

    def set_enforced(self, enabled: bool) -> None:
        self._force = bool(enabled)

    # ── CRUD ────────────────────────────────────────────────────────────
    def _dispatch_budget_alert_webhook(self, url: str, payload: Dict[str, Any]) -> None:
        """Asynchronously dispatches an HTTP POST webhook alert on budget events without blocking requests."""
        def _post():
            try:
                import urllib.request
                import json
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "VeloRoute-Gateway/2.0"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    logger.info(f"[VirtualKey] Budget webhook delivered to {url} (status={resp.status})")
            except Exception as err:
                logger.warning(f"[VirtualKey] Failed to dispatch budget alert webhook to {url}: {err}")

        threading.Thread(target=_post, daemon=True).start()

    async def create_key(
        self,
        name: str,
        *,
        budget_usd: Optional[float] = None,
        budget_alert_threshold: Optional[float] = None,
        budget_alert_webhook: Optional[str] = None,
        auto_pause_on_budget: bool = True,
        rpm_limit: Optional[int] = None,
        tpm_limit: Optional[int] = None,
        allowed_models: Optional[List[str]] = None,
        expires_at: Optional[float] = None,
        expires_in: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
        raw_key: Optional[str] = None,
    ) -> Tuple[VirtualKey, str]:
        """Create a key. Returns ``(record, plaintext_key)`` exactly once."""
        if not name or not str(name).strip():
            raise ValueError("Virtual key name is required")
        if budget_usd is not None and float(budget_usd) < 0:
            raise ValueError("budget_usd must be >= 0")
        if rpm_limit is not None and int(rpm_limit) <= 0:
            raise ValueError("rpm_limit must be > 0")
        if tpm_limit is not None and int(tpm_limit) <= 0:
            raise ValueError("tpm_limit must be > 0")

        if expires_at is None and expires_in is not None:
            expires_at = _now() + float(expires_in)

        plaintext = raw_key or (KEY_PREFIX + secrets.token_urlsafe(32))
        digest = _hash(plaintext, self._pepper)

        with self._lock:
            if digest in self._by_hash:
                raise ValueError("A key with this value already exists")
            record = VirtualKey(
                id="vk_" + uuid.uuid4().hex[:12],
                name=str(name).strip(),
                key_hash=digest,
                key_prefix=_display_prefix(plaintext),
                enabled=bool(enabled),
                expires_at=expires_at,
                budget_usd=float(budget_usd) if budget_usd is not None else None,
                budget_alert_threshold=float(budget_alert_threshold) if budget_alert_threshold is not None else None,
                budget_alert_webhook=str(budget_alert_webhook).strip() if budget_alert_webhook else None,
                auto_pause_on_budget=bool(auto_pause_on_budget),
                rpm_limit=int(rpm_limit) if rpm_limit is not None else None,
                tpm_limit=int(tpm_limit) if tpm_limit is not None else None,
                allowed_models=[str(m) for m in (allowed_models or [])],
                metadata=dict(metadata or {}),
            )
            self._keys[record.id] = record
            self._by_hash[digest] = record.id
            self._dirty = True

        await self.save()
        return record, plaintext

    def get_key(self, key_id: str) -> Optional[VirtualKey]:
        with self._lock:
            return self._keys.get(key_id)

    def list_keys(self, include_revoked: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            records = sorted(self._keys.values(), key=lambda k: k.created_at)
            return [
                r.to_public_dict()
                for r in records
                if include_revoked or r.revoked_at is None
            ]

    async def update_key(self, key_id: str, **fields: Any) -> Optional[VirtualKey]:
        """Update mutable fields. Unknown fields are ignored."""
        allowed = {
            "name", "enabled", "expires_at", "expires_in", "budget_usd",
            "budget_alert_threshold", "budget_alert_webhook", "auto_pause_on_budget",
            "rpm_limit", "tpm_limit", "allowed_models", "metadata",
        }
        with self._lock:
            record = self._keys.get(key_id)
            if record is None:
                return None
            for field_name, value in fields.items():
                if field_name not in allowed:
                    continue
                if field_name == "expires_in":
                    if value is None:
                        continue
                    record.expires_at = _now() + float(value)
                elif field_name == "budget_usd":
                    record.budget_usd = float(value) if value is not None else None
                    record.alert_sent = False
                elif field_name == "budget_alert_threshold":
                    record.budget_alert_threshold = float(value) if value is not None else None
                    record.alert_sent = False
                elif field_name == "budget_alert_webhook":
                    record.budget_alert_webhook = str(value).strip() if value else None
                elif field_name == "auto_pause_on_budget":
                    if value is not None:
                        record.auto_pause_on_budget = bool(value)
                elif field_name == "rpm_limit":
                    record.rpm_limit = int(value) if value is not None else None
                elif field_name == "tpm_limit":
                    record.tpm_limit = int(value) if value is not None else None
                elif field_name == "allowed_models":
                    record.allowed_models = [str(m) for m in (value or [])]
                elif field_name == "metadata":
                    record.metadata = dict(value or {})
                elif field_name == "enabled":
                    if value is not None:
                        record.enabled = bool(value)
                elif field_name == "expires_at":
                    record.expires_at = float(value) if value else None
                elif field_name == "name":
                    if value is not None:
                        record.name = str(value).strip() or record.name
            self._dirty = True
            result = record
        await self.save()
        return result

    async def revoke_key(self, key_id: str) -> bool:
        with self._lock:
            record = self._keys.get(key_id)
            if record is None:
                return False
            record.enabled = False
            record.revoked_at = _now()
            self._dirty = True
        await self.save()
        return True

    async def delete_key(self, key_id: str) -> bool:
        with self._lock:
            record = self._keys.pop(key_id, None)
            if record is None:
                return False
            self._by_hash.pop(record.key_hash, None)
            self._windows.pop(key_id, None)
            self._dirty = True
        await self.save()
        return True

    async def rotate_key(self, key_id: str) -> Optional[str]:
        """Invalidate the old secret and return a new plaintext key."""
        plaintext = KEY_PREFIX + secrets.token_urlsafe(32)
        digest = _hash(plaintext, self._pepper)
        with self._lock:
            record = self._keys.get(key_id)
            if record is None:
                return None
            self._by_hash.pop(record.key_hash, None)
            record.key_hash = digest
            record.key_prefix = _display_prefix(plaintext)
            record.revoked_at = None
            record.enabled = True
            self._by_hash[digest] = key_id
            self._dirty = True
        await self.save()
        return plaintext

    async def clear_all(self) -> int:
        """Remove every key (used by tests and administrative reset)."""
        with self._lock:
            count = len(self._keys)
            self._keys.clear()
            self._by_hash.clear()
            self._windows.clear()
            self._dirty = True
        await self.save()
        return count

    # ── authentication / authorization ──────────────────────────────────
    def _find_by_plaintext(self, raw_key: Optional[str]) -> Optional[VirtualKey]:
        if not raw_key:
            return None
        digest = _hash(raw_key, self._pepper)
        with self._lock:
            key_id = self._by_hash.get(digest)
            if key_id is None:
                return None
            record = self._keys.get(key_id)
            if record is None:
                return None
            # Constant-time comparison even though the dict lookup already
            # matched; protects against accidental non-constant-time changes.
            if not hmac.compare_digest(record.key_hash, digest):
                return None
            return record

    def _check_static(
        self,
        record: VirtualKey,
        model: str,
        resolved_model: Optional[str],
        *,
        check_model: bool = True,
        budget_pricing_available: bool = True,
    ) -> None:
        if record.revoked_at is not None:
            raise GatewayAuthError(401, "key_revoked", "This API key has been revoked.")
        if not record.enabled:
            raise GatewayAuthError(403, "key_disabled", "This API key is disabled.")
        if record.is_expired:
            raise GatewayAuthError(401, "key_expired", "This API key has expired.")
        if record.budget_usd is not None and record.spent_usd >= record.budget_usd:
            raise GatewayAuthError(
                402,
                "budget_exceeded",
                f"Budget of ${record.budget_usd:.4f} exhausted for this API key.",
            )
        if (
            record.budget_usd is not None
            and model
            and not budget_pricing_available
        ):
            raise GatewayAuthError(
                400,
                "unpriced_model",
                f"Cannot enforce this API key's budget because no compatible price is configured for '{model}'.",
            )
        if record.allowed_models and check_model:
            candidates = [c for c in (model, resolved_model) if c]
            all_candidates = set(candidates)
            for c in candidates:
                if "/" in c:
                    all_candidates.add(c.split("/", 1)[1])
            if not any(
                fnmatch.fnmatchcase(candidate, pattern)
                for candidate in all_candidates
                for pattern in record.allowed_models
            ):
                raise GatewayAuthError(
                    403,
                    "model_not_allowed",
                    f"API key is not permitted to use model '{model}'.",
                )

    def _check_rate_limits(
        self,
        record: VirtualKey,
        estimated_tokens: int,
        now: float,
        reservation_id: Optional[str] = None,
    ) -> None:
        window = self._windows.setdefault(record.id, _KeyWindow())
        window.prune(now)

        if record.rpm_limit and len(window.requests) >= record.rpm_limit:
            retry_after = max(
                1, int(WINDOW_SECONDS - (now - window.requests[0])) + 1
            )
            raise GatewayAuthError(
                429,
                "rate_limit_exceeded",
                f"Request rate limit of {record.rpm_limit} RPM exceeded.",
                headers={"Retry-After": str(retry_after)},
            )

        if record.tpm_limit:
            projected = window.token_total() + max(0, int(estimated_tokens))
            if projected > record.tpm_limit:
                timestamps = [timestamp for timestamp, _ in window.tokens]
                timestamps.extend(
                    timestamp for timestamp, _ in window.reservations.values()
                )
                oldest = min(timestamps, default=now)
                retry_after = max(1, int(WINDOW_SECONDS - (now - oldest)) + 1)
                raise GatewayAuthError(
                    429,
                    "token_rate_limit_exceeded",
                    f"Token rate limit of {record.tpm_limit} TPM exceeded.",
                    headers={"Retry-After": str(retry_after)},
                )

        # Reserve the request slot and prompt-token estimate immediately so
        # concurrent requests cannot all slip through the same window.
        window.requests.append(now)
        if estimated_tokens:
            if reservation_id:
                window.reservations[reservation_id] = (now, int(estimated_tokens))
            else:
                window.tokens.append((now, int(estimated_tokens)))

    def pop_queued_ms(self, reservation_id: Optional[str]) -> int:
        """Return and remove any rate-limit queuing latency (ms) for this reservation."""
        if not reservation_id:
            return 0
        with self._lock:
            return self._queued_ms.pop(reservation_id, 0)

    async def _authorize(
        self,
        raw_key: Optional[str],
        *,
        model: str = "",
        resolved_model: Optional[str] = None,
        estimated_tokens: int = 0,
        reservation_id: Optional[str] = None,
        check_model: bool = True,
        budget_pricing_available: bool = True,
        queue_timeout: float = 0.0,
    ) -> VirtualKey:
        if not raw_key:
            raise GatewayAuthError(
                401,
                "missing_api_key",
                "Missing API key. Provide it via 'Authorization: Bearer <key>' or 'x-api-key'.",
            )
        record = self._find_by_plaintext(raw_key)
        if record is None:
            raise GatewayAuthError(401, "invalid_api_key", "Invalid API key.")
        now = _now()
        with self._lock:
            self._check_static(
                record,
                model,
                resolved_model,
                check_model=check_model,
                budget_pricing_available=budget_pricing_available,
            )
            try:
                self._check_rate_limits(record, estimated_tokens, now, reservation_id)
                rate_limited = False
            except GatewayAuthError as gae:
                if gae.status_code != 429 or queue_timeout <= 0:
                    raise
                rate_limited = True
                first_exc = gae

        if rate_limited:
            deadline = time.monotonic() + queue_timeout
            start_q = time.monotonic()
            resolved = False
            while time.monotonic() < deadline:
                import asyncio
                await asyncio.sleep(0.05)
                now = _now()
                with self._lock:
                    try:
                        self._check_rate_limits(record, estimated_tokens, now, reservation_id)
                        resolved = True
                        queued_dur = max(1, int((time.monotonic() - start_q) * 1000))
                        if reservation_id:
                            self._queued_ms[reservation_id] = queued_dur
                        break
                    except GatewayAuthError as retry_exc:
                        if retry_exc.status_code != 429:
                            raise
                        first_exc = retry_exc
            if not resolved:
                raise first_exc

        return record

    async def authorize(
        self,
        raw_key: Optional[str],
        *,
        model: str = "",
        resolved_model: Optional[str] = None,
        estimated_tokens: int = 0,
        check_model: bool = True,
        budget_pricing_available: bool = True,
        queue_timeout: float = 0.0,
    ) -> VirtualKey:
        """
        Validate a plaintext key and reserve rate-limit capacity.

        Raises :class:`GatewayAuthError` on any failure.  This method never
        touches storage; it is safe to call on the hot path.
        """
        return await self._authorize(
            raw_key,
            model=model,
            resolved_model=resolved_model,
            estimated_tokens=estimated_tokens,
            check_model=check_model,
            budget_pricing_available=budget_pricing_available,
            queue_timeout=queue_timeout,
        )

    async def authorize_with_reservation(
        self,
        raw_key: Optional[str],
        *,
        model: str = "",
        resolved_model: Optional[str] = None,
        estimated_tokens: int = 0,
        check_model: bool = True,
        budget_pricing_available: bool = True,
        queue_timeout: float = 0.0,
    ) -> Tuple[VirtualKey, str]:
        """Authorize a request and return an ID for reconciling its token estimate."""
        reservation_id = uuid.uuid4().hex
        record = await self._authorize(
            raw_key,
            model=model,
            resolved_model=resolved_model,
            estimated_tokens=estimated_tokens,
            reservation_id=reservation_id,
            check_model=check_model,
            budget_pricing_available=budget_pricing_available,
            queue_timeout=queue_timeout,
        )
        return record, reservation_id

    # ── usage accounting ────────────────────────────────────────────────
    async def record_usage(
        self,
        key_id: str,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        reserved_tokens: int = 0,
        reservation_id: Optional[str] = None,
        count_estimate_when_missing: bool = True,
    ) -> Optional[VirtualKey]:
        """Reconcile actual usage and (throttled) persist it."""
        now = _now()
        with self._lock:
            record = self._keys.get(key_id)
            if record is None:
                return None
            prompt_tokens = max(0, int(prompt_tokens or 0))
            completion_tokens = max(0, int(completion_tokens or 0))
            total = prompt_tokens + completion_tokens
            record.total_requests += 1
            record.total_prompt_tokens += prompt_tokens
            record.total_completion_tokens += completion_tokens
            record.total_tokens += total
            record.spent_usd += max(0.0, float(cost_usd or 0.0))
            record.last_used_at = now

            # Budget threshold alerts and auto-pause check
            if record.budget_usd and record.budget_usd > 0:
                spend_ratio = record.spent_usd / record.budget_usd
                threshold = record.budget_alert_threshold or 0.80

                # Soft warning threshold
                if spend_ratio >= threshold and not record.alert_sent:
                    record.alert_sent = True
                    logger.warning(
                        f"[VirtualKey] Budget warning: Key '{record.name}' ({record.key_prefix}) has spent "
                        f"${record.spent_usd:.4f} / ${record.budget_usd:.4f} ({spend_ratio*100:.1f}%)"
                    )
                    if record.budget_alert_webhook:
                        self._dispatch_budget_alert_webhook(
                            record.budget_alert_webhook,
                            {
                                "event": "virtual_key.budget_threshold",
                                "key_id": record.id,
                                "key_name": record.name,
                                "key_prefix": record.key_prefix,
                                "spent_usd": round(record.spent_usd, 6),
                                "budget_usd": record.budget_usd,
                                "spend_ratio": round(spend_ratio, 4),
                                "threshold": threshold,
                                "timestamp": now,
                            }
                        )

                # Hard quota auto-pause
                if record.spent_usd >= record.budget_usd and record.auto_pause_on_budget and record.enabled:
                    record.enabled = False
                    logger.warning(
                        f"[VirtualKey] Budget exhausted: Key '{record.name}' ({record.key_prefix}) auto-paused. "
                        f"Spent ${record.spent_usd:.4f} >= ${record.budget_usd:.4f}"
                    )
                    if record.budget_alert_webhook:
                        self._dispatch_budget_alert_webhook(
                            record.budget_alert_webhook,
                            {
                                "event": "virtual_key.budget_exhausted",
                                "key_id": record.id,
                                "key_name": record.name,
                                "key_prefix": record.key_prefix,
                                "spent_usd": round(record.spent_usd, 6),
                                "budget_usd": record.budget_usd,
                                "timestamp": now,
                            }
                        )

            window = self._windows.setdefault(key_id, _KeyWindow())
            window.prune(now)
            if reservation_id:
                reservation = window.reservations.pop(reservation_id, None)
                if total:
                    window.tokens.append((now, total))
                elif reservation and reservation[1] and count_estimate_when_missing:
                    # Providers without token-usage fields still count the
                    # estimate that was reserved for this request.
                    window.tokens.append((now, reservation[1]))
            else:
                delta = total - max(0, int(reserved_tokens or 0))
                if delta > 0:
                    window.tokens.append((now, delta))
            self._dirty = True
            result = record

        await self._maybe_persist(now)
        return result

    def get_usage(self, key_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._keys.get(key_id)
            if record is None:
                return None
            window = self._windows.get(key_id)
            if window:
                window.prune(_now())
            return {
                **record.to_public_dict(),
                "window_requests": len(window.requests) if window else 0,
                "window_tokens": window.token_total() if window else 0,
            }

    def stats(self) -> Dict[str, Any]:
        now = _now()
        with self._lock:
            records = list(self._keys.values())
            return {
                "enforcement_enabled": self._force or bool(records),
                "forced": self._force,
                "total_keys": len(records),
                "active_keys": sum(1 for r in records if r.is_active),
                "revoked_keys": sum(1 for r in records if r.revoked_at is not None),
                "disabled_keys": sum(1 for r in records if not r.enabled),
                "expired_keys": sum(
                    1 for r in records if r.expires_at is not None and now >= r.expires_at
                ),
                "total_requests": sum(r.total_requests for r in records),
                "total_tokens": sum(r.total_tokens for r in records),
                "total_spend_usd": round(sum(r.spent_usd for r in records), 8),
            }

    # ── persistence ─────────────────────────────────────────────────────
    async def save(self) -> None:
        """Persist the full key set. Failures are logged, never fatal."""
        if self.storage is None or getattr(self.storage, "_backend", True) is None:
            with self._lock:
                self._dirty = False
            return
        with self._lock:
            payload = {
                "version": 1,
                "updated_at": _now(),
                "keys": [r.to_store_dict() for r in self._keys.values()],
            }
            self._dirty = False
        try:
            await self.storage.save_config(PERSIST_KEY, payload)
            self._last_saved = _now()
        except Exception as exc:  # pragma: no cover - storage-specific
            with self._lock:
                self._dirty = True
            logger.warning("Virtual key persistence failed (non-fatal): %s", exc)

    async def _maybe_persist(self, now: float) -> None:
        if self.storage is None or getattr(self.storage, "_backend", True) is None or not self._dirty:
            return
        if now - self._last_saved < self.persist_interval:
            return
        await self.save()

    async def flush(self) -> None:
        """Force a persist if there are unsaved changes."""
        with self._lock:
            dirty = self._dirty
        if dirty:
            await self.save()

    async def load(self) -> int:
        """Load persisted keys. Returns the number of records loaded."""
        if self.storage is None or getattr(self.storage, "_backend", True) is None:
            return 0
        try:
            config = await self.storage.get_config(PERSIST_KEY)
        except Exception as exc:  # pragma: no cover - storage-specific
            logger.warning("Virtual key load failed (non-fatal): %s", exc)
            return 0
        if config is None:
            return 0
        raw = config.value if hasattr(config, "value") else config
        items = (raw or {}).get("keys", []) if isinstance(raw, dict) else []
        loaded = 0
        with self._lock:
            for item in items:
                try:
                    record = VirtualKey.from_store_dict(item)
                except Exception:
                    logger.warning("Skipping malformed virtual key record")
                    continue
                if record.id in self._keys or record.key_hash in self._by_hash:
                    continue
                self._keys[record.id] = record
                self._by_hash[record.key_hash] = record.id
                loaded += 1
            if loaded:
                self._dirty = False
        return loaded


__all__ = [
    "GatewayAuthError",
    "VirtualKey",
    "VirtualKeyManager",
    "PERSIST_KEY",
]
