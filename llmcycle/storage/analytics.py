"""
Analytics engine — works across all backends by querying saved LLMRequests.
Supports filtering by: time range, user, session, team, provider, model.
"""
from __future__ import annotations
import time
from typing import Optional, List, Dict, Any
from llmcycle.storage.base import BaseStorage


class Analytics:
    """
    Rich analytics over stored LLM request data.

    All methods accept optional filters:
        from_ts   — Unix timestamp start (inclusive)
        to_ts     — Unix timestamp end   (inclusive)
        user_id   — filter by user
        session_id— filter by session
        team_id   — filter by team (needs requests to have team via session lookup)
        provider  — filter by provider name
        model     — filter by model name

    Usage:
        stats = await client.storage.analytics.summary(
            from_ts=yesterday, user_id="u-123"
        )
    """

    def __init__(self, backend: BaseStorage):
        self._b = backend

    async def _fetch(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 10_000,
    ):
        """Fetch and filter requests from backend."""
        from llmcycle.storage.models import LLMRequest
        reqs = await self._b.list_requests(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
        )
        # Apply extra filters in-process
        if from_ts:
            reqs = [r for r in reqs if r.created_at >= from_ts]
        if to_ts:
            reqs = [r for r in reqs if r.created_at <= to_ts]
        if provider:
            reqs = [r for r in reqs if r.provider == provider]
        if model:
            reqs = [r for r in reqs if r.model == model]
        return reqs

    async def summary(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        High-level summary across any filter combination.

        Returns:
            {
                "total_requests": 120,
                "total_prompt_tokens": 45000,
                "total_completion_tokens": 12000,
                "total_tokens": 57000,
                "avg_latency_ms": 342.1,
                "p95_latency_ms": 890.2,
                "error_rate": 0.025,      # 2.5%
                "fallback_rate": 0.083,   # 8.3%
                "success_count": 117,
                "error_count": 3,
                "fallback_count": 10,
                "period_seconds": 86400,
            }
        """
        reqs = await self._fetch(from_ts, to_ts, user_id, session_id, provider, model)
        return self._compute_summary(reqs, from_ts, to_ts)

    def _compute_summary(self, reqs, from_ts, to_ts) -> Dict[str, Any]:
        if not reqs:
            return {"total_requests": 0}
        n = len(reqs)
        latencies = sorted(r.latency_ms for r in reqs)
        p95_idx = max(0, int(n * 0.95) - 1)
        errors = sum(1 for r in reqs if r.status == "error")
        fallbacks = sum(1 for r in reqs if r.fallback_used)
        prompt_tok = sum(r.prompt_tokens for r in reqs)
        comp_tok = sum(r.completion_tokens for r in reqs)
        period = (to_ts or time.time()) - (from_ts or reqs[-1].created_at) if from_ts or to_ts else None
        return {
            "total_requests": n,
            "total_prompt_tokens": prompt_tok,
            "total_completion_tokens": comp_tok,
            "total_tokens": prompt_tok + comp_tok,
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "p95_latency_ms": round(latencies[p95_idx], 2),
            "min_latency_ms": round(latencies[0], 2),
            "max_latency_ms": round(latencies[-1], 2),
            "success_count": n - errors,
            "error_count": errors,
            "fallback_count": fallbacks,
            "error_rate": round(errors / n, 4),
            "fallback_rate": round(fallbacks / n, 4),
            "period_seconds": round(period, 1) if period else None,
        }

    async def by_provider(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Breakdown per provider.

        Returns:
            [
              {"provider": "openai", "requests": 80, "tokens": 44000, "avg_latency_ms": 310, "errors": 1},
              {"provider": "groq",   "requests": 40, "tokens": 13000, "avg_latency_ms": 95,  "errors": 0},
            ]
        """
        reqs = await self._fetch(from_ts, to_ts, user_id, session_id)
        groups: Dict[str, list] = {}
        for r in reqs:
            groups.setdefault(r.provider, []).append(r)
        result = []
        for prov, rs in sorted(groups.items(), key=lambda x: -len(x[1])):
            lats = [r.latency_ms for r in rs]
            result.append({
                "provider": prov,
                "requests": len(rs),
                "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rs),
                "prompt_tokens": sum(r.prompt_tokens for r in rs),
                "completion_tokens": sum(r.completion_tokens for r in rs),
                "avg_latency_ms": round(sum(lats) / len(lats), 2),
                "errors": sum(1 for r in rs if r.status == "error"),
                "fallbacks": sum(1 for r in rs if r.fallback_used),
            })
        return result

    async def by_model(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Breakdown per model, sorted by usage."""
        reqs = await self._fetch(from_ts, to_ts, user_id)
        groups: Dict[str, list] = {}
        for r in reqs:
            groups.setdefault(r.model, []).append(r)
        return [
            {
                "model": m,
                "requests": len(rs),
                "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rs),
                "avg_latency_ms": round(sum(r.latency_ms for r in rs) / len(rs), 2),
            }
            for m, rs in sorted(groups.items(), key=lambda x: -len(x[1]))
        ]

    async def by_user(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        provider: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Breakdown per user, sorted by token usage."""
        reqs = await self._fetch(from_ts, to_ts, provider=provider)
        groups: Dict[str, list] = {}
        for r in reqs:
            uid = r.user_id or "anonymous"
            groups.setdefault(uid, []).append(r)
        return [
            {
                "user_id": uid,
                "requests": len(rs),
                "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rs),
                "sessions": len(set(r.session_id for r in rs if r.session_id)),
                "errors": sum(1 for r in rs if r.status == "error"),
            }
            for uid, rs in sorted(groups.items(), key=lambda x: -sum(r.prompt_tokens + r.completion_tokens for r in x[1]))
        ]

    async def by_session(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Breakdown per session."""
        reqs = await self._fetch(from_ts, to_ts, user_id=user_id)
        groups: Dict[str, list] = {}
        for r in reqs:
            sid = r.session_id or "no-session"
            groups.setdefault(sid, []).append(r)
        return [
            {
                "session_id": sid,
                "requests": len(rs),
                "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rs),
                "models_used": list(set(r.model for r in rs)),
                "providers_used": list(set(r.provider for r in rs)),
                "duration_s": round(max(r.created_at for r in rs) - min(r.created_at for r in rs), 1),
            }
            for sid, rs in sorted(groups.items(), key=lambda x: -len(x[1]))
        ]

    async def timeseries(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        user_id: Optional[str] = None,
        bucket: str = "hour",  # "minute" | "hour" | "day"
    ) -> List[Dict[str, Any]]:
        """
        Time-bucketed request counts and token usage.

        Returns list of:
            {"bucket": "2025-05-22T14:00", "requests": 12, "tokens": 4200, "errors": 0}
        """
        import datetime
        reqs = await self._fetch(from_ts, to_ts, user_id=user_id)
        fmt = {"minute": "%Y-%m-%dT%H:%M", "hour": "%Y-%m-%dT%H:00", "day": "%Y-%m-%d"}.get(bucket, "%Y-%m-%dT%H:00")
        groups: Dict[str, list] = {}
        for r in reqs:
            key = datetime.datetime.utcfromtimestamp(r.created_at).strftime(fmt)
            groups.setdefault(key, []).append(r)
        return [
            {
                "bucket": k,
                "requests": len(rs),
                "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rs),
                "errors": sum(1 for r in rs if r.status == "error"),
                "avg_latency_ms": round(sum(r.latency_ms for r in rs) / len(rs), 2),
            }
            for k, rs in sorted(groups.items())
        ]

    async def top_errors(
        self,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Most common errors with counts."""
        reqs = await self._fetch(from_ts, to_ts)
        errors = [r for r in reqs if r.status == "error" and r.error]
        counts: Dict[str, int] = {}
        for r in errors:
            counts[r.error] = counts.get(r.error, 0) + 1
        return [
            {"error": e, "count": c, "provider": next((r.provider for r in errors if r.error == e), "?")}
            for e, c in sorted(counts.items(), key=lambda x: -x[1])[:limit]
        ]
