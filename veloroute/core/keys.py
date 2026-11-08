"""
KeyManager - Production Multi-Key Rotation
==========================================
Supports:
 - Round-robin across multiple keys
 - Rate-limit cooldown per key (auto re-enable after cooldown)
 - Permanent disable on auth failure (401)
 - Per-key error tracking with thresholds
"""
from __future__ import annotations
import time
import threading
import hashlib
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

RATE_LIMIT_COOLDOWN_SECS = 30.0
QUOTA_COOLDOWN_SECS = 30.0
DEFAULT_FAILURE_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECS = 30.0

class KeyStatus(Enum):
    ACTIVE          = "active"
    RATE_LIMITED    = "rate_limited"     # 429 – temporary, retry after cooldown
    QUOTA_EXHAUSTED = "quota_exhausted"  # 402/429 quota – long cooldown
    CIRCUIT_BROKEN  = "circuit_broken"   # 5xx/connection error spike – auto-trip
    INVALID         = "invalid"          # 401 – permanent disable
    DISABLED        = "disabled"         # manual disable

@dataclass
class KeyRecord:
    key: str
    provider: str
    status: KeyStatus = KeyStatus.ACTIVE
    total_requests: int = 0
    total_successes: int = 0
    total_errors: int = 0
    consecutive_errors: int = 0
    circuit_trips: int = 0
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    circuit_cooldown_secs: float = CIRCUIT_COOLDOWN_SECS
    circuit_trip_until: float = 0.0
    circuit_state: str = "closed"        # "closed" | "open" | "half_open"
    half_open_success_threshold: int = 1 # Consecutive successes required to close from half_open
    half_open_successes: int = 0
    recent_outcomes: List[bool] = field(default_factory=list) # Rolling window of recent outcomes (max 20)
    probe_in_flight: bool = False
    rate_limit_until: float = 0.0
    added_at: float = field(default_factory=time.time)
    last_used: float = 0.0

    @property
    def recent_failure_rate(self) -> float:
        """Sliding-window failure rate (0.0 to 1.0) over recent requests."""
        outcomes = list(self.recent_outcomes)
        if not outcomes:
            return 0.0
        failures = sum(1 for o in outcomes if not o)
        return round(failures / len(outcomes), 2)


    @property
    def key_hint(self) -> str:
        """Safe display: show first 6 and last 4 chars, or partial for shorter keys."""
        if len(self.key) <= 6:
            return "***"
        if len(self.key) <= 10:
            return f"{self.key[:2]}...{self.key[-2:]}"
        return f"{self.key[:6]}...{self.key[-4:]}"

    @property
    def is_usable(self) -> bool:
        if self.status == KeyStatus.ACTIVE:
            return True
        if self.status in (KeyStatus.RATE_LIMITED, KeyStatus.QUOTA_EXHAUSTED):
            return time.time() >= self.rate_limit_until
        if self.status == KeyStatus.CIRCUIT_BROKEN:
            # When cooldown expires, key enters half_open and can be probed (if no probe currently in-flight)
            if time.time() >= self.circuit_trip_until:
                self.circuit_state = "half_open"
                return not self.probe_in_flight
            return False
        return False


class KeyManager:
    """Thread-safe multi-key manager with auto rotation, circuit breaking, and error classification."""

    def __init__(self):
        self._lock = threading.RLock()
        # provider → list of KeyRecord (in insertion order for round-robin)
        self._keys: Dict[str, List[KeyRecord]] = {}
        # Round-robin pointer per provider
        self._indexes: Dict[str, int] = {}

    def add_key(self, provider: str, key: str) -> None:
        """Register one API key for a provider."""
        p = provider.lower()
        with self._lock:
            if p not in self._keys:
                self._keys[p] = []
                self._indexes[p] = 0
            # Don't add duplicates
            existing = {r.key for r in self._keys[p]}
            if key not in existing:
                self._keys[p].append(KeyRecord(key=key, provider=p))
                logger.debug(f"[{p}] Registered key {KeyRecord(key=key, provider=p).key_hint}")

    def add_keys(self, provider: str, keys: List[str]) -> None:
        for k in keys:
            self.add_key(provider, k)

    def get_next_key(self, provider: str, strategy: str = "round_robin") -> Optional[str]:
        """
        Key rotation with auto-recovery.
        Supports strategy: "round_robin" (default) or "least_used".
        """
        p = provider.lower()
        with self._lock:
            records = self._keys.get(p, [])
            if not records:
                return None

            now = time.time()
            # 1. Perform auto-recovery checks on all keys for provider
            for rec in records:
                if rec.status in (KeyStatus.RATE_LIMITED, KeyStatus.QUOTA_EXHAUSTED):
                    if now >= rec.rate_limit_until:
                        rec.status = KeyStatus.ACTIVE
                        rec.consecutive_errors = 0
                        logger.info(f"[{p}] Key {rec.key_hint} auto-recovered from {rec.status.value}")
                elif rec.status == KeyStatus.CIRCUIT_BROKEN:
                    if now >= rec.circuit_trip_until:
                        rec.circuit_state = "half_open"

            # 2. Strategy: Least-Used
            if strategy == "least_used":
                usable = [r for r in records if r.is_usable]
                if not usable:
                    logger.warning(f"[{p}] No usable keys available (least_used)!")
                    return None
                # Pick key with lowest request count, breaking ties by oldest last_used
                selected = min(usable, key=lambda r: (r.total_requests, r.last_used))
                selected.last_used = time.time()
                selected.total_requests += 1
                if selected.status == KeyStatus.CIRCUIT_BROKEN or selected.circuit_state == "half_open":
                    selected.probe_in_flight = True
                    selected.circuit_state = "half_open"
                return selected.key

            # 3. Strategy: Round-Robin (default)
            n = len(records)
            start = self._indexes.get(p, 0)

            for i in range(n):
                idx = (start + i) % n
                rec = records[idx]

                if rec.is_usable:
                    self._indexes[p] = (idx + 1) % n
                    rec.last_used = time.time()
                    rec.total_requests += 1
                    if rec.status == KeyStatus.CIRCUIT_BROKEN or rec.circuit_state == "half_open":
                        rec.probe_in_flight = True
                        rec.circuit_state = "half_open"
                    return rec.key

            # 4. Self-Healing Fallback: If all keys are in temporary cooldown or circuit breaker,
            # don't leave the user stranded! Pick the best candidate (not permanently invalid)
            # to serve as an opportunistic probe. If daily quota refreshed or user selected
            # a working model, report_success will immediately reactivate the key!
            candidates = [r for r in records if r.status not in (KeyStatus.INVALID, KeyStatus.DISABLED)]
            if candidates:
                rec = min(candidates, key=lambda r: (r.rate_limit_until, r.circuit_trip_until, r.last_used))
                rec.last_used = time.time()
                return rec.key

            logger.warning(f"[{p}] No usable keys available!")
            return None

    get_key = get_next_key

    def peek_key(self, provider: str, include_unusable: bool = False) -> Optional[str]:
        """
        Return a key for read-only operations (model discovery, diagnostics)
        WITHOUT incrementing request counters, changing round-robin position,
        consuming a half-open probe, or updating ``last_used``.
        """
        p = provider.lower()
        with self._lock:
            records = self._keys.get(p, [])
            if not records:
                return None
            now = time.time()
            for rec in records:
                if rec.status in (KeyStatus.RATE_LIMITED, KeyStatus.QUOTA_EXHAUSTED):
                    if now >= rec.rate_limit_until:
                        rec.status = KeyStatus.ACTIVE
                        rec.consecutive_errors = 0
                elif rec.status == KeyStatus.CIRCUIT_BROKEN and now >= rec.circuit_trip_until:
                    rec.circuit_state = "half_open"
                if rec.is_usable:
                    return rec.key
            return records[0].key if include_unusable else None

    def report_success(self, provider: str, key: str) -> None:
        with self._lock:
            rec = self._find(provider, key)
            if rec:
                rec.consecutive_errors = 0
                rec.total_successes += 1
                rec.probe_in_flight = False
                rec.recent_outcomes.append(True)
                if len(rec.recent_outcomes) > 20:
                    rec.recent_outcomes.pop(0)

                if rec.status == KeyStatus.CIRCUIT_BROKEN or rec.circuit_state in ("open", "half_open"):
                    rec.half_open_successes += 1
                    if rec.half_open_successes >= rec.half_open_success_threshold:
                        rec.status = KeyStatus.ACTIVE
                        rec.circuit_state = "closed"
                        rec.circuit_trip_until = 0.0
                        rec.circuit_trips = 0
                        rec.half_open_successes = 0
                        logger.info(f"[{provider}] Key {rec.key_hint} circuit breaker recovered -> closed")

    def report_error(self, provider: str, key: str, error_type: str) -> None:
        """
        error_type: "rate_limit" | "quota" | "auth" | "server" | "connection" | "timeout"
        """
        with self._lock:
            rec = self._find(provider, key)
            if not rec:
                return

            rec.total_errors += 1
            rec.consecutive_errors += 1
            rec.probe_in_flight = False
            rec.recent_outcomes.append(False)
            if len(rec.recent_outcomes) > 20:
                rec.recent_outcomes.pop(0)
            rec.half_open_successes = 0

            if error_type == "auth":
                rec.status = KeyStatus.INVALID
                rec.circuit_state = "open"
                logger.warning(f"[{provider}] Key {rec.key_hint} permanently disabled (401 Auth)")

            elif error_type == "quota":
                rec.status = KeyStatus.QUOTA_EXHAUSTED
                rec.rate_limit_until = time.time() + QUOTA_COOLDOWN_SECS
                logger.warning(f"[{provider}] Key {rec.key_hint} quota exhausted. Retry after {QUOTA_COOLDOWN_SECS}s")

            elif error_type == "rate_limit":
                rec.status = KeyStatus.RATE_LIMITED
                rec.rate_limit_until = time.time() + RATE_LIMIT_COOLDOWN_SECS
                logger.warning(f"[{provider}] Key {rec.key_hint} rate limited. Retry after {RATE_LIMIT_COOLDOWN_SECS}s")

            elif error_type in ("server", "connection", "timeout", "5xx"):
                # Resilient Circuit Breaker: Auto-trip when consecutive errors reach failure_threshold, or if probe fails in half_open
                should_trip = False
                trip_reason = ""

                if rec.status == KeyStatus.CIRCUIT_BROKEN or rec.circuit_state == "half_open":
                    should_trip = True
                    trip_reason = "failed half-open probe"
                elif rec.consecutive_errors >= rec.failure_threshold:
                    should_trip = True
                    trip_reason = f"{rec.consecutive_errors} consecutive errors"
                elif len(rec.recent_outcomes) >= 10 and rec.recent_failure_rate >= 0.7:
                    should_trip = True
                    trip_reason = f"high error rate ({rec.recent_failure_rate * 100:.0f}% over recent window)"

                if should_trip:
                    rec.status = KeyStatus.CIRCUIT_BROKEN
                    rec.circuit_state = "open"
                    rec.circuit_trips += 1
                    cooldown = min(600.0, rec.circuit_cooldown_secs * (2 ** min(6, rec.circuit_trips - 1)))
                    rec.circuit_trip_until = time.time() + cooldown
                    logger.warning(
                        f"[{provider}] Key {rec.key_hint} circuit breaker TRIPPED ({trip_reason}). "
                        f"Cooldown for {cooldown:.1f}s (trip #{rec.circuit_trips})"
                    )
                else:
                    logger.debug(
                        f"[{provider}] Key {rec.key_hint} got {error_type} error "
                        f"({rec.consecutive_errors}/{rec.failure_threshold} before circuit breaker trip)"
                    )

    def reset_circuit_breaker(self, provider: Optional[str] = None) -> int:
        """Reset circuit-broken and cooldown keys back to ACTIVE status."""
        reset_count = 0
        with self._lock:
            targets = [provider.lower()] if provider else list(self._keys.keys())
            for p in targets:
                for rec in self._keys.get(p, []):
                    if rec.status in (KeyStatus.CIRCUIT_BROKEN, KeyStatus.QUOTA_EXHAUSTED, KeyStatus.RATE_LIMITED) or rec.circuit_state != "closed":
                        rec.status = KeyStatus.ACTIVE
                        rec.circuit_state = "closed"
                        rec.consecutive_errors = 0
                        rec.circuit_trips = 0
                        rec.circuit_trip_until = 0.0
                        rec.rate_limit_until = 0.0
                        rec.probe_in_flight = False
                        rec.half_open_successes = 0
                        rec.recent_outcomes.clear()
                        reset_count += 1
        return reset_count

    def get_circuit_breaker_status(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Detailed Sentinel-style circuit breaker diagnostics across all providers and keys."""
        now = time.time()
        with self._lock:
            targets = [provider.lower()] if provider else sorted(self._keys.keys())
            report: Dict[str, Any] = {}
            for p in targets:
                records = self._keys.get(p, [])
                keys_info = []
                broken_count = 0
                for r in records:
                    if r.status == KeyStatus.CIRCUIT_BROKEN or r.circuit_state != "closed":
                        broken_count += 1
                    cd_remaining = max(0.0, round(r.circuit_trip_until - now, 1)) if r.circuit_trip_until > now else 0.0
                    rl_remaining = max(0.0, round(r.rate_limit_until - now, 1)) if r.rate_limit_until > now else 0.0
                    keys_info.append({
                        "key_hint": r.key_hint,
                        "status": r.status.value,
                        "circuit_state": r.circuit_state,
                        "circuit_trips": r.circuit_trips,
                        "consecutive_errors": r.consecutive_errors,
                        "recent_failure_rate": r.recent_failure_rate,
                        "total_requests": r.total_requests,
                        "total_successes": r.total_successes,
                        "total_errors": r.total_errors,
                        "cooldown_remaining_secs": cd_remaining or rl_remaining,
                        "is_usable": r.is_usable,
                    })
                report[p] = {
                    "provider": p,
                    "provider_circuit_state": self.get_provider_circuit_state(p),
                    "total_keys": len(records),
                    "active_keys": sum(1 for r in records if r.is_usable),
                    "circuit_broken_keys": broken_count,
                    "keys": keys_info,
                }
            return report


    def get_stats(self, provider: str) -> List[dict]:
        p = provider.lower()
        with self._lock:
            return [
                {
                    "hint": r.key_hint,
                    "status": r.status.value,
                    "total_requests": r.total_requests,
                    "total_successes": r.total_successes,
                    "total_errors": r.total_errors,
                    "consecutive_errors": r.consecutive_errors,
                    "circuit_state": r.circuit_state,
                    "circuit_trips": r.circuit_trips,
                    "last_used": r.last_used,
                }
                for r in self._keys.get(p, [])
            ]


    def list_providers(self) -> List[str]:
        return list(self._keys.keys())

    def set_keys(self, provider: str, keys: List[str]) -> None:
        """Replace all keys for a provider with a new list of keys."""
        p = provider.lower()
        with self._lock:
            self._keys[p] = [KeyRecord(key=k.strip(), provider=p) for k in keys if k.strip()]
            self._indexes[p] = 0
            logger.info(f"[{p}] Set {len(self._keys[p])} keys")

    def remove_provider(self, provider: str) -> bool:
        """Remove a provider and all its keys."""
        p = provider.lower()
        with self._lock:
            removed = p in self._keys
            self._keys.pop(p, None)
            self._indexes.pop(p, None)
            if removed:
                logger.info(f"[{p}] Removed from KeyManager")
            return removed

    def remove_key(self, provider: str, key_or_hint: str) -> bool:
        """Remove a single key matching exact string or key_hint."""
        p = provider.lower()
        with self._lock:
            records = self._keys.get(p, [])
            match_idx = -1
            for i, r in enumerate(records):
                if r.key == key_or_hint or r.key_hint == key_or_hint:
                    match_idx = i
                    break
            if match_idx >= 0:
                removed_rec = records.pop(match_idx)
                if records:
                    self._indexes[p] = self._indexes.get(p, 0) % len(records)
                else:
                    self._indexes[p] = 0
                logger.info(f"[{p}] Removed key {removed_rec.key_hint}")
                return True
            return False

    def key_count(self, provider: str) -> dict:
        p = provider.lower()
        with self._lock:
            records = self._keys.get(p, [])
            return {
                "total": len(records),
                "active": sum(1 for r in records if r.is_usable),
                "invalid": sum(1 for r in records if r.status == KeyStatus.INVALID),
                "rate_limited": sum(1 for r in records if r.status in (KeyStatus.RATE_LIMITED, KeyStatus.QUOTA_EXHAUSTED)),
                "circuit_broken": sum(1 for r in records if r.status == KeyStatus.CIRCUIT_BROKEN),
            }

    def has_active_keys(self, provider: str) -> bool:
        """Returns True if the provider has at least one usable key."""
        p = provider.lower()
        with self._lock:
            records = self._keys.get(p, [])
            return any(r.is_usable for r in records)

    def is_provider_healthy(self, provider: str) -> bool:
        """Returns True if provider has at least one active or usable key."""
        return self.has_active_keys(provider)

    def get_provider_circuit_state(self, provider: str) -> str:
        """
        Provider-level circuit breaker state:
        'closed': healthy active key available.
        'half_open': probing key in progress.
        'open': all keys circuit-broken or exhausted.
        'no_keys': no keys registered.
        """
        p = provider.lower()
        with self._lock:
            records = self._keys.get(p, [])
            if not records:
                return "no_keys"
            if any(r.status == KeyStatus.ACTIVE for r in records):
                return "closed"
            if any(r.circuit_state == "half_open" for r in records):
                return "half_open"
            if any(r.is_usable for r in records):
                return "closed"
            return "open"

    def _find(self, provider: str, key: str) -> Optional[KeyRecord]:
        p = provider.lower()
        with self._lock:
            for rec in self._keys.get(p, []):
                if rec.key == key:
                    return rec
        return None
