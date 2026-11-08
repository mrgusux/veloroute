from __future__ import annotations
from collections import deque
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from veloroute.core.router import RoutingStrategy
from .deps import auth, llm_client
from .models import SetFallbackRequest, AliasRequest

router = APIRouter()

@router.get("/api/v1/router")
async def get_router(_: str = Depends(auth)):
    return {
        "strategy": llm_client.router.strategy.value,
        "fallbacks": llm_client.router.fallbacks,
        "aliases": llm_client.list_aliases(),
        "latencies": llm_client.router.latency.all(),
        "available_strategies": [s.value for s in RoutingStrategy],
        "feedback_summary": llm_client.router.get_feedback_stats(),
    }

@router.post("/api/v1/router/fallbacks")
async def set_fallbacks(req: SetFallbackRequest, _: str = Depends(auth)):
    llm_client.router.fallbacks = req.fallbacks
    try:
        await llm_client.router.save()
    except Exception:
        pass
    return {"status": "ok", "fallbacks": req.fallbacks}

@router.get("/api/v1/router/aliases")
async def get_aliases(_: str = Depends(auth)):
    return {"aliases": llm_client.list_aliases()}

@router.post("/api/v1/router/aliases")
async def set_alias(req: AliasRequest, _: str = Depends(auth)):
    if not req.name or not req.target:
        raise HTTPException(400, "Missing 'name' or 'target' for alias")
    llm_client.alias(req.name, req.target)
    try:
        await llm_client.router.save()
    except Exception:
        pass
    return {"status": "ok", "alias": req.name, "target": req.target}

@router.delete("/api/v1/router/aliases/{name}")
async def delete_alias(name: str, _: str = Depends(auth)):
    removed = llm_client.remove_alias(name)
    if not removed:
        raise HTTPException(404, f"Alias '{name}' not found")
    try:
        await llm_client.router.save()
    except Exception:
        pass
    return {"status": "ok", "message": f"Alias '{name}' removed"}


class SetStrategyRequest(BaseModel):
    strategy: Optional[str] = None


class CanaryConfigRequest(BaseModel):
    enabled: bool = True
    primary_model: str = ""
    canary_model: str = ""
    weight: float = 20.0
    canary_weight: Optional[float] = None


class ShadowConfigRequest(BaseModel):
    enabled: bool = True
    primary_model: str = ""
    shadow_model: str = ""
    sample_rate: float = 100.0


class GuardrailConfigRequest(BaseModel):
    pii_mode: Optional[str] = None  # off | redact | block
    mode: Optional[str] = None      # UI alias for pii_mode
    injection_protection: bool = False
    injection_threshold: float = Field(default=0.7, ge=0.1, le=1.0)
    entropy_threshold: float = Field(default=3.8, ge=2.0, le=6.0)


class GuardrailTestRequest(BaseModel):
    prompt: str
    mode: str = "redact"
    entropy_threshold: float = 3.8
    injection_threshold: float = 0.7


class FeedbackRequest(BaseModel):
    target: Optional[str] = None
    model: Optional[str] = None
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rating: Optional[int] = None
    comment: Optional[str] = ""
    trace_id: Optional[str] = ""


# Global runtime traffic-shaping & security policies wired directly into proxy.py, anthropic.py, and console.py
_RUNTIME_CANARY: Dict[str, Any] = {
    "enabled": False,
    "primary_model": "",
    "canary_model": "",
    "weight": 20.0,
    "canary_weight": 20.0,
}

_RUNTIME_SHADOW: Dict[str, Any] = {
    "enabled": False,
    "primary_model": "",
    "shadow_model": "",
    "sample_rate": 100.0,
}

_SHADOW_HISTORY: deque = deque(maxlen=50)

_GLOBAL_GUARDRAIL_CONFIG: Dict[str, Any] = {
    "pii_mode": "off",
    "mode": "off",
    "injection_protection": False,
    "injection_threshold": 0.7,
    "entropy_threshold": 3.8,
}

_SECURITY_AUDIT_LOG: deque = deque(maxlen=100)


def record_shadow_execution(entry: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
    payload: Dict[str, Any] = {}
    if isinstance(entry, dict):
        payload.update(entry)
    payload.update(kwargs)
    payload.setdefault("timestamp", time.time())
    if "latency_ms" not in payload:
        payload["latency_ms"] = payload.get("shadow_latency_ms", payload.get("primary_latency_ms", 0.0))
    raw_status = str(payload.get("status", "ok")).lower()
    if raw_status == "success":
        payload["status"] = "ok"
    _SHADOW_HISTORY.appendleft(payload)


def record_security_audit(
    event_type: str = "security_scan",
    action: str = "sanitized",
    model: str = "",
    pii_count: int = 0,
    pii_labels: Optional[List[str]] = None,
    injection_score: float = 0.0,
    masked_preview: str = "",
    score: Optional[float] = None,
    matches: Optional[List[str]] = None,
    trace_id: str = "",
    endpoint: str = "",
    detail: str = "",
    **extra: Any,
) -> None:
    """Append a zero-raw-PII security compliance event to the audit log."""
    eff_score = round(float(injection_score if injection_score else (score or 0.0)), 3)
    labels = list(pii_labels or [])
    if not detail:
        if matches:
            detail = f"Injection patterns: {', '.join(str(m) for m in matches)}"
        elif pii_count > 0:
            lbl_str = f" ({', '.join(labels[:4])})" if labels else ""
            detail = f"PII/Secret entities detected: {pii_count}{lbl_str}"
        else:
            detail = f"{event_type} ({action})"
    _SECURITY_AUDIT_LOG.appendleft({
        "timestamp": time.time(),
        "event_type": event_type,
        "action": action,
        "endpoint": endpoint or (f"/v1/chat/completions [{model}]" if model else "/v1/chat/completions"),
        "detail": detail,
        "model": model,
        "pii_count": pii_count,
        "pii_labels": labels,
        "injection_score": eff_score,
        "masked_preview": (masked_preview or "")[:140],
        "trace_id": trace_id,
    })


@router.get("/api/v1/router/canary")
async def get_canary_config(_: str = Depends(auth)):
    return _RUNTIME_CANARY


@router.post("/api/v1/router/canary")
async def set_canary_config(req: CanaryConfigRequest, _: str = Depends(auth)):
    raw_w = req.canary_weight if req.canary_weight is not None else req.weight
    w = max(1.0, min(100.0, float(raw_w)))
    _RUNTIME_CANARY["enabled"] = bool(req.enabled and req.canary_model.strip())
    _RUNTIME_CANARY["primary_model"] = req.primary_model.strip()
    _RUNTIME_CANARY["canary_model"] = req.canary_model.strip()
    _RUNTIME_CANARY["weight"] = w
    _RUNTIME_CANARY["canary_weight"] = w
    return {"status": "ok", "canary": _RUNTIME_CANARY}


@router.get("/api/v1/router/shadow")
async def get_shadow_config(_: str = Depends(auth)):
    return {**_RUNTIME_SHADOW, "history_count": len(_SHADOW_HISTORY)}


@router.post("/api/v1/router/shadow")
async def set_shadow_config(req: ShadowConfigRequest, _: str = Depends(auth)):
    _RUNTIME_SHADOW["enabled"] = bool(req.enabled and req.shadow_model.strip())
    _RUNTIME_SHADOW["primary_model"] = req.primary_model.strip()
    _RUNTIME_SHADOW["shadow_model"] = req.shadow_model.strip()
    _RUNTIME_SHADOW["sample_rate"] = max(1.0, min(100.0, float(req.sample_rate)))
    return {"status": "ok", "shadow": _RUNTIME_SHADOW}


@router.get("/api/v1/router/shadow/history")
async def get_shadow_history(_: str = Depends(auth)):
    return {"history": list(_SHADOW_HISTORY)}


@router.post("/api/v1/router/shadow/clear")
async def clear_shadow_history(_: str = Depends(auth)):
    count = len(_SHADOW_HISTORY)
    _SHADOW_HISTORY.clear()
    return {"status": "ok", "cleared": count}


@router.get("/api/v1/guardrails/info")
async def get_guardrails_info(_: str = Depends(auth)):
    return {
        "status": "active",
        "pii_patterns": [
            "Email Address",
            "Social Security Number (SSN)",
            "Credit Card",
            "IPv4/IPv6 Address",
            "OpenAI / Anthropic / VeloRoute API Keys",
            "AWS Access Keys (AKIA/ASIA)",
            "GitHub PAT & Slack Tokens",
            "JWTs & PEM Private Keys",
            "High-Entropy Secrets",
        ],
        "injection_protection": f"Heuristic Classifier (threshold {_GLOBAL_GUARDRAIL_CONFIG['injection_threshold']})",
        "modes": ["off", "redact", "block"],
        "config": _GLOBAL_GUARDRAIL_CONFIG,
    }


@router.get("/api/v1/guardrails/config")
async def get_guardrails_config(_: str = Depends(auth)):
    return dict(_GLOBAL_GUARDRAIL_CONFIG)


@router.post("/api/v1/guardrails/config")
async def set_guardrails_config(req: GuardrailConfigRequest, _: str = Depends(auth)):
    chosen = req.mode if req.mode is not None else (req.pii_mode if req.pii_mode is not None else "off")
    mode = chosen.lower().strip()
    if mode not in ("off", "redact", "block"):
        raise HTTPException(400, "pii_mode must be 'off', 'redact', or 'block'")
    _GLOBAL_GUARDRAIL_CONFIG["pii_mode"] = mode
    _GLOBAL_GUARDRAIL_CONFIG["mode"] = mode
    _GLOBAL_GUARDRAIL_CONFIG["injection_protection"] = bool(req.injection_protection)
    _GLOBAL_GUARDRAIL_CONFIG["injection_threshold"] = round(float(req.injection_threshold), 2)
    _GLOBAL_GUARDRAIL_CONFIG["entropy_threshold"] = round(float(req.entropy_threshold), 2)
    return {"status": "ok", "config": dict(_GLOBAL_GUARDRAIL_CONFIG)}


@router.get("/api/v1/guardrails/audit")
async def get_guardrails_audit(_: str = Depends(auth)):
    return {"events": list(_SECURITY_AUDIT_LOG), "total": len(_SECURITY_AUDIT_LOG)}


@router.post("/api/v1/guardrails/audit/clear")
async def clear_guardrails_audit(_: str = Depends(auth)):
    count = len(_SECURITY_AUDIT_LOG)
    _SECURITY_AUDIT_LOG.clear()
    return {"status": "ok", "cleared": count}


@router.post("/api/v1/guardrails/test")
async def test_guardrail(req: GuardrailTestRequest, _: str = Depends(auth)):
    from veloroute.core.guardrail import GuardrailManager
    from veloroute.core.injection import InjectionGuard

    # 1. PII Test
    mgr = GuardrailManager(entropy_threshold=req.entropy_threshold)
    masked = mgr.mask_prompt(req.prompt)
    unmasked = mgr.unmask_response(masked)

    # 2. Injection Test
    inj_guard = InjectionGuard(threshold=req.injection_threshold)
    inj_res = inj_guard.scan(req.prompt)

    if mgr.counter > 0 or inj_res.blocked:
        record_security_audit(
            event_type="sandbox_scan",
            action="blocked" if (inj_res.blocked or (req.mode == "block" and mgr.counter > 0)) else "sanitized",
            endpoint="/api/v1/guardrails/test",
            model="sandbox",
            pii_count=mgr.counter,
            pii_labels=list(mgr.mask_to_secret.keys()),
            injection_score=inj_res.score,
            matches=inj_res.matches,
            masked_preview=masked,
        )

    return {
        "original_prompt": req.prompt,
        "masked_prompt": masked,
        "unmasked_prompt": unmasked,
        "pii_detected_count": mgr.counter,
        "pii_items": list(mgr.mask_to_secret.keys()),
        "injection_score": inj_res.score,
        "injection_blocked": inj_res.blocked,
        "injection_matches": inj_res.matches,
    }


@router.post("/api/v1/feedback")
async def submit_quality_feedback(req: FeedbackRequest, _: str = Depends(auth)):
    target_name = (req.target or req.model or "").strip()
    if not target_name:
        raise HTTPException(400, "Missing 'target' or 'model' identifier")
    if req.score is not None:
        eff_score = float(req.score)
    elif req.rating is not None:
        eff_score = 1.0 if req.rating > 0 else (0.0 if req.rating < 0 else 0.5)
    else:
        eff_score = 1.0
    rec = llm_client.router.record_feedback(
        target=target_name,
        score=eff_score,
        comment=req.comment or "",
        trace_id=req.trace_id or "",
    )
    try:
        await llm_client.router.save()
    except Exception:
        pass
    return {
        "status": "ok",
        "quality_score": rec.get("new_score", 0.5),
        "record": rec,
    }


@router.get("/api/v1/feedback/stats")
async def get_quality_feedback_stats(_: str = Depends(auth)):
    return llm_client.router.get_feedback_stats()


@router.get("/api/v1/router/topology")
async def get_routing_topology(_: str = Depends(auth)):
    """Return live gateway routing architecture graph (Archify-style topology) + route diagnostics."""
    providers_info = []
    diagnostics = []
    for p_name in llm_client.key_manager.list_providers():
        counts = llm_client.key_manager.key_count(p_name)
        lat = llm_client.router.latency.get(p_name)
        qual = llm_client.router.quality.get_score(p_name)
        healthy = counts.get("active", 0) > 0
        if not healthy:
            diagnostics.append(f"Provider '{p_name}' has 0 active keys (degraded/exhausted).")
        providers_info.append({
            "name": p_name,
            "healthy": healthy,
            "active_keys": counts.get("active", 0),
            "total_keys": counts.get("total", 0),
            "latency_ms": round(lat, 1) if lat < 900000 else None,
            "quality_score": round(qual, 2),
        })

    groups_dict = {}
    if hasattr(llm_client.router, "groups") and llm_client.router.groups:
        groups_dict = dict(getattr(llm_client.router.groups, "_groups", {}) or {})
    groups_list = [{"id": k, "models": list(v)} for k, v in groups_dict.items()]

    return {
        "strategy": llm_client.router.strategy.value,
        "guardrails": dict(_GLOBAL_GUARDRAIL_CONFIG),
        "semantic_cache_enabled": llm_client._semantic_cache is not None,
        "canary": dict(_RUNTIME_CANARY),
        "shadow": dict(_RUNTIME_SHADOW),
        "aliases": llm_client.list_aliases(),
        "groups": groups_list,
        "groups_map": groups_dict,
        "fallbacks": dict(llm_client.router.fallbacks),
        "providers": providers_info,
        "diagnostics": diagnostics,
    }


@router.api_route("/api/v1/router/strategy", methods=["PUT", "POST"])
async def set_strategy(strategy: Optional[str] = Query(None), req: Optional[SetStrategyRequest] = None, _: str = Depends(auth)):
    chosen_strategy = strategy or (req.strategy if req else None)
    if not chosen_strategy:
        raise HTTPException(400, "Missing 'strategy' parameter in query or body")
    try:
        llm_client.router.strategy = RoutingStrategy(chosen_strategy)
        try:
            await llm_client.router.save()
        except Exception:
            pass
        return {"status": "ok", "strategy": chosen_strategy}
    except ValueError:
        valid = ", ".join(s.value for s in RoutingStrategy)
        raise HTTPException(400, f"Unknown strategy '{chosen_strategy}'. Use: {valid}")


@router.get("/api/v1/routing/latency_matrix")
async def get_latency_matrix(_: str = Depends(auth)):
    matrix = llm_client.router.latency.get_all_matrix()
    return {"matrix": matrix, "total": len(matrix)}


@router.post("/api/v1/routing/latency_matrix/probe_all")
async def probe_all_latencies(_: str = Depends(auth)):
    import asyncio
    providers = list(llm_client._providers.keys())

    async def probe(p_name: str):
        try:
            prov = llm_client._providers.get(p_name)
            if prov:
                key = llm_client.key_manager.peek_key(p_name) or ""
                ping_res = await prov.ping(key)
                if isinstance(ping_res, dict) and ping_res.get("status") == "ok":
                    lat = float(ping_res.get("latency_ms", 1.0))
                    llm_client.router.latency.record(p_name, lat, success=True)
                    return {"provider": p_name, "latency_ms": round(lat, 1), "status": "healthy"}
                elif isinstance(ping_res, (int, float)) and ping_res < 999999:
                    lat = float(ping_res)
                    llm_client.router.latency.record(p_name, lat, success=True)
                    return {"provider": p_name, "latency_ms": round(lat, 1), "status": "healthy"}
                else:
                    llm_client.router.latency.record(p_name, 0.0, success=False)
                    return {"provider": p_name, "latency_ms": None, "status": "down"}
        except Exception as e:
            llm_client.router.latency.record(p_name, 0.0, success=False)
            return {"provider": p_name, "error": str(e), "status": "down"}

    results = await asyncio.gather(*(probe(p) for p in providers), return_exceptions=False)
    matrix = llm_client.router.latency.get_all_matrix()
    return {"status": "complete", "matrix": matrix, "probe_results": results}


