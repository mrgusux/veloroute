from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
import os
from pathlib import Path
from .deps import auth, llm_client
from .models import GroupRequest, ProxyRequest
from veloroute.cli import _set_env_key, _remove_env_key, _safe_load_env

router = APIRouter()

@router.get("/api/v1/dashboard")
async def dashboard(_: str = Depends(auth)):
    providers_out = []
    for name in llm_client.get_providers():
        counts = llm_client.key_manager.key_count(name)
        key_stats = llm_client.key_manager.get_stats(name)
        latency = llm_client.router.latency.get(name)
        custom_m = llm_client.get_custom_models(name)
        circuit_st = llm_client.key_manager.get_provider_circuit_state(name)
        providers_out.append({
            "name": name,
            "base_url": llm_client._providers[name].base_url,
            "keys": counts,
            "key_stats": key_stats,
            "circuit_state": circuit_st,
            "latency_ms": round(latency, 1) if latency < 999999 else None,
            "custom_models": custom_m,
            "is_custom": custom_m is not None,
        })
    groups_count = len(llm_client.router.groups.list_all()) if hasattr(llm_client.router, "groups") and hasattr(llm_client.router.groups, "list_all") else 0
    return {
        "providers": providers_out,
        "fallbacks": llm_client.router.fallbacks,
        "aliases": llm_client.list_aliases(),
        "strategy": llm_client.router.strategy.value,
        "total_providers": len(providers_out),
        "total_active_keys": sum(llm_client.key_manager.key_count(p)["active"] for p in llm_client.get_providers()),
        "total_tripped_keys": sum(llm_client.key_manager.key_count(p).get("circuit_broken", 0) for p in llm_client.get_providers()),
        "total_groups": groups_count,
    }

@router.get("/api/v1/system")
async def get_system_status(_: str = Depends(auth)):
    storage_name = "Memory (RAM)"
    if llm_client.storage:
        cls_name = llm_client.storage.__class__.__name__
        if "SQL" in cls_name or cls_name == "StorageManager":
            storage_name = "SQLite (Disk)"
        else:
            storage_name = cls_name
    return {
        "storage": storage_name,
        "config_loader": "env",
        "semantic_cache": getattr(llm_client, "_semantic_cache", None) is not None,
    }

@router.get("/api/v1/proxy")
async def get_proxy(_: str = Depends(auth)):
    return {"proxy": llm_client.proxy, "proxy_url": llm_client.proxy}

@router.post("/api/v1/proxy")
async def set_proxy(req: ProxyRequest, _: str = Depends(auth)):
    proxy_val = req.proxy.strip() if req.proxy else None
    if not proxy_val:
        proxy_val = None
    
    # Update the proxy on the client
    llm_client.proxy = proxy_val
    
    # Update the proxy on all currently initialized providers
    for provider in llm_client._providers.values():
        provider.proxy = proxy_val
        
    # Auto-persist to .env
    try:
        env_path = Path(".env")
        if proxy_val:
            _set_env_key(env_path, "VELOROUTE_PROXY", proxy_val)
            os.environ["VELOROUTE_PROXY"] = proxy_val
        else:
            _remove_env_key(env_path, "VELOROUTE_PROXY")
            os.environ.pop("VELOROUTE_PROXY", None)
        _safe_load_env()
    except Exception:
        pass

    return {"status": "ok", "proxy": proxy_val, "proxy_url": proxy_val}

@router.delete("/api/v1/proxy")
async def clear_proxy(_: str = Depends(auth)):
    llm_client.proxy = None
    for provider in llm_client._providers.values():
        provider.proxy = None
    try:
        env_path = Path(".env")
        _remove_env_key(env_path, "VELOROUTE_PROXY")
        os.environ.pop("VELOROUTE_PROXY", None)
        _safe_load_env()
    except Exception:
        pass
    return {"status": "ok", "proxy": None, "proxy_url": None}

@router.get("/api/v1/groups")
async def get_groups(_: str = Depends(auth)):
    groups_out = []
    for g_id, models in llm_client.router.groups.list_all().items():
        groups_out.append({
            "id": g_id,
            "models": models,
            "strategy": None,
        })
    return groups_out

@router.post("/api/v1/groups")
async def set_group(req: GroupRequest, _: str = Depends(auth)):
    await llm_client.router.groups.set_async(req.name, req.models)
    return {"status": "ok", "group": req.name, "models": req.models}

@router.delete("/api/v1/groups/{name}")
async def delete_group(name: str, _: str = Depends(auth)):
    removed = await llm_client.router.groups.remove_async(name)
    if not removed:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"status": "ok", "message": f"Group {name} removed"}

@router.get("/api/v1/detected_env_providers")
async def get_detected_env_providers(_: str = Depends(auth)):
    detected = []
    for k in os.environ.keys():
        if k.endswith("_API_KEYS"):
            prov = k[:-9].lower()
            if prov not in detected:
                detected.append(prov)
        elif k.endswith("_API_KEY"):
            prov = k[:-8].lower()
            if prov not in detected:
                detected.append(prov)
    return {"detected": detected}

@router.post("/api/v1/providers/auto_register")
async def auto_register_env_providers(_: str = Depends(auth)):
    llm_client._auto_load_configs()
    return {"status": "ok", "providers": llm_client.get_providers()}

# ─── Analytics endpoints ───────────────────────────────────────────────────────
@router.get("/api/v1/analytics/data")
async def get_analytics_data(_: str = Depends(auth)):
    if not llm_client.storage or not getattr(llm_client.storage, "analytics", None):
        return {
            "summary": {"total_requests": 0, "success_count": 0, "error_count": 0},
            "by_provider": [],
            "by_model": [],
            "timeseries": [],
            "top_errors": []
        }
    
    engine = llm_client.storage.analytics
    # Fetch most recent 2,000 requests to guarantee high speed and avoid database timeouts
    reqs = await engine._fetch(limit=2000)
    
    if not reqs:
        return {
            "summary": {"total_requests": 0, "success_count": 0, "error_count": 0},
            "by_provider": [],
            "by_model": [],
            "timeseries": [],
            "top_errors": []
        }
        
    summary = engine._compute_summary(reqs, from_ts=None, to_ts=None)
    
    # Providers breakdown
    prov_groups = {}
    for r in reqs:
        prov_groups.setdefault(r.provider, []).append(r)
    by_provider = []
    for prov, rs in sorted(prov_groups.items(), key=lambda x: -len(x[1])):
        lats = [r.latency_ms for r in rs]
        by_provider.append({
            "provider": prov,
            "requests": len(rs),
            "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rs),
            "avg_latency_ms": round(sum(lats) / len(lats), 2),
            "errors": sum(1 for r in rs if r.status == "error"),
        })
        
    # Models breakdown
    model_groups = {}
    for r in reqs:
        model_groups.setdefault(r.model, []).append(r)
    by_model = []
    for m, rs in sorted(model_groups.items(), key=lambda x: -len(x[1])):
        by_model.append({
            "model": m,
            "requests": len(rs),
            "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rs),
            "avg_latency_ms": round(sum(r.latency_ms for r in rs) / len(rs), 2),
        })
        
    # Timeseries
    import datetime
    time_groups = {}
    for r in reqs:
        key = datetime.datetime.fromtimestamp(r.created_at, datetime.timezone.utc).strftime("%Y-%m-%dT%H:00")
        time_groups.setdefault(key, []).append(r)
    timeseries = []
    for k, rs in sorted(time_groups.items()):
        timeseries.append({
            "bucket": k,
            "requests": len(rs),
            "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rs),
            "avg_latency_ms": round(sum(r.latency_ms for r in rs) / len(rs), 2),
        })
        
    # Top errors
    errors_list = [r for r in reqs if r.status == "error" and r.error]
    error_counts = {}
    for r in errors_list:
        error_counts[r.error] = error_counts.get(r.error, 0) + 1
    top_errors = [
        {"error": e, "count": c, "provider": next((r.provider for r in errors_list if r.error == e), "?")}
        for e, c in sorted(error_counts.items(), key=lambda x: -x[1])[:10]
    ]
    
    return {
        "summary": summary,
        "by_provider": by_provider,
        "by_model": by_model,
        "timeseries": timeseries,
        "top_errors": top_errors
    }

@router.get("/api/v1/analytics/keys")
async def get_key_analytics(_: str = Depends(auth)):
    """Detailed per-key usage, success/error rates, and circuit breaker status across all providers."""
    key_metrics = []
    providers = llm_client.get_providers()
    for prov in providers:
        stats = llm_client.key_manager.get_stats(prov)
        for s in stats:
            reqs = s.get("total_requests", 0)
            succs = s.get("total_successes", 0)
            errs = s.get("total_errors", 0)
            rate = round((succs / reqs) * 100, 1) if reqs > 0 else 100.0
            key_metrics.append({
                "provider": prov,
                "hint": s.get("hint"),
                "status": s.get("status"),
                "circuit_state": s.get("circuit_state", "closed"),
                "circuit_trips": s.get("circuit_trips", 0),
                "total_requests": reqs,
                "total_successes": succs,
                "total_errors": errs,
                "consecutive_errors": s.get("consecutive_errors", 0),
                "success_rate_pct": rate,
                "last_used": s.get("last_used", 0.0),
            })
    return {
        "total_keys": len(key_metrics),
        "keys": key_metrics,
    }

@router.post("/api/v1/circuit_breaker/reset")
async def reset_circuit_breaker(provider: Optional[str] = Query(None), _: str = Depends(auth)):
    """Reset circuit-broken keys back to ACTIVE status."""
    reset_count = llm_client.key_manager.reset_circuit_breaker(provider)
    return {"status": "ok", "reset_keys": reset_count, "provider": provider or "all"}


@router.get("/api/v1/circuit_breaker/status")
async def get_circuit_breaker_status(provider: Optional[str] = Query(None), _: str = Depends(auth)):
    """Sentinel-style circuit breaker diagnostics and health metrics."""
    return llm_client.key_manager.get_circuit_breaker_status(provider)


@router.get("/api/v1/privacy/status")
async def get_privacy_status(_: str = Depends(auth)):
    """Retrieve current Zero-Retention Privacy Mode status."""
    return {
        "enabled": getattr(llm_client, "privacy_mode", False),
        "mode": "zero_retention",
        "description": "Zero retention mode: No prompts, completions, or tool payloads are stored or logged.",
    }


@router.post("/api/v1/privacy/toggle")
async def toggle_privacy_mode(_: str = Depends(auth)):
    """Toggle Zero-Retention Privacy Mode on or off for the live session."""
    current = getattr(llm_client, "privacy_mode", False)
    llm_client.privacy_mode = not current
    return {
        "enabled": llm_client.privacy_mode,
        "mode": "zero_retention",
        "message": f"Zero-retention privacy mode {'enabled' if llm_client.privacy_mode else 'disabled'}.",
    }


@router.post("/api/v1/context/optimize")
async def optimize_context(request: Request, _: str = Depends(auth)):
    """Token-Saviour lossless context compression, terminal trimming, AST chunking, and Caveman terse mode."""
    data = await request.json()
    text = data.get("text", "")
    messages = data.get("messages")
    skeletonize = bool(data.get("skeletonize", False))
    trim_terminal = bool(data.get("trim_terminal", True))
    normalize_ws = bool(data.get("normalize_ws", True))
    terse = bool(data.get("terse", False) or data.get("caveman", False))

    opt = getattr(llm_client, "context_optimizer", None)
    if not opt:
        from veloroute.core.context_optimizer import ContextOptimizer
        opt = ContextOptimizer()

    if messages and isinstance(messages, list):
        opt_messages, stats = opt.optimize_messages(
            messages,
            skeletonize_python=skeletonize,
            terse_mode=terse,
        )
        return {
            "messages": opt_messages,
            "stats": stats,
        }

    res = opt.optimize_text(
        text,
        skeletonize_python=skeletonize,
        trim_terminal=trim_terminal,
        normalize_ws=normalize_ws,
        terse_mode=terse,
    )
    return res


@router.post("/api/v1/hooks/claude-code/prompt-submit")
@router.post("/api/v1/prompt/size-hook")
async def claude_code_hook(request: Request):
    """Claude Code UserPromptSubmit and developer agent task sizing hook."""
    payload = await request.json()
    sizer = getattr(llm_client, "prompt_sizer", None)
    if not sizer:
        from veloroute.core.prompt_sizer import PromptSizer
        sizer = PromptSizer()
    return sizer.handle_hook_request(payload)


@router.get("/api/v1/quickstart/snippets")
async def get_quickstart_snippets(request: Request, _: str = Depends(auth)):
    """Drop-in developer migration snippets for Python, Node, cURL, and CLI coding agents."""
    host = request.headers.get("host", "localhost:8000")
    base_url = f"http://{host}"

    vkey = "sk-velo-YOUR_VIRTUAL_KEY"
    vkey_hint = ""
    vkeys = getattr(llm_client, "virtual_keys", None)
    if vkeys and hasattr(vkeys, "keys") and vkeys.keys:
        for vk in vkeys.keys.values():
            if getattr(vk, "is_active", True):
                vkey_hint = getattr(vk, "masked_key", "")
                break

    return {
        "host": host,
        "base_url": base_url,
        "virtual_key": vkey,
        "snippets": {
            "openai_python": f'''from openai import OpenAI

client = OpenAI(
    base_url="{base_url}/v1",
    api_key="{vkey}",
)

response = client.chat.completions.create(
    model="smart",
    messages=[{{"role": "user", "content": "Hello VeloRoute!"}}],
)
print(response.choices[0].message.content)''',
            "anthropic_python": f'''import anthropic

client = anthropic.Anthropic(
    base_url="{base_url}/p/anthropic",
    api_key="{vkey}",
)

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{{"role": "user", "content": "Hello VeloRoute!"}}],
)
print(message.content[0].text)''',
            "curl": f'''curl {base_url}/v1/chat/completions \\
  -H "Authorization: Bearer {vkey}" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "model": "smart",
    "messages": [{{"role": "user", "content": "Hello VeloRoute!"}}]
  }}\'''',
            "claude_code": f'''# Configure Claude Code CLI:
export ANTHROPIC_BASE_URL="{base_url}"
export ANTHROPIC_API_KEY="{vkey}"
claude''',
        }
    }


async def _collect_recent_traces(limit: int = 50):
    """Collect recent request traces from storage analytics or in-memory metrics ring buffer."""
    items = []
    if llm_client.storage and getattr(llm_client.storage, "analytics", None):
        try:
            reqs = await llm_client.storage.analytics._fetch(limit=limit)
            for r in reqs:
                lat_ms = float(getattr(r, "latency_ms", 0.0) or 0.0)
                p_tok = int(getattr(r, "prompt_tokens", 0) or 0)
                c_tok = int(getattr(r, "completion_tokens", 0) or 0)
                t_tok = int(getattr(r, "total_tokens", 0) or (p_tok + c_tok))
                tps = round(c_tok / (lat_ms / 1000.0), 1) if lat_ms > 0 and c_tok > 0 else 0.0
                cost = getattr(r, "cost_usd", None)
                if cost is None:
                    cost = llm_client._estimate_cost(getattr(r, "model", ""), p_tok, c_tok) or 0.0
                ts_val = getattr(r, "created_at", 0.0)
                items.append({
                    "id": getattr(r, "id", ""),
                    "created_at": ts_val,
                    "timestamp": ts_val,
                    "provider": getattr(r, "provider", "unknown"),
                    "model": getattr(r, "model", "unknown"),
                    "status": getattr(r, "status", "success"),
                    "latency_ms": round(lat_ms, 1),
                    "ttft_ms": getattr(r, "time_to_first_token_ms", None),
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "total_tokens": t_tok,
                    "tokens_per_sec": tps,
                    "cost_usd": round(float(cost), 6),
                    "fallback_used": bool(getattr(r, "fallback_used", False)),
                    "is_cached": bool(getattr(r, "is_cached", False)),
                    "error": getattr(r, "error", None),
                })
        except Exception:
            pass

    if not items and hasattr(llm_client, "metrics") and hasattr(llm_client.metrics, "_recent_traces"):
        for t in list(llm_client.metrics._recent_traces)[:limit]:
            lat_ms = float(t.get("latency_ms", 0.0) or 0.0)
            p_tok = int(t.get("prompt_tokens", 0) or 0)
            c_tok = int(t.get("completion_tokens", 0) or 0)
            t_tok = int(t.get("total_tokens", 0) or (p_tok + c_tok))
            tps = round(c_tok / (lat_ms / 1000.0), 1) if lat_ms > 0 and c_tok > 0 else 0.0
            model_name = str(t.get("model", "unknown"))
            cost = llm_client._estimate_cost(model_name, p_tok, c_tok) or 0.0
            ts_val = t.get("created_at", t.get("timestamp", 0.0))
            items.append({
                "id": t.get("id", ""),
                "created_at": ts_val,
                "timestamp": ts_val,
                "provider": t.get("provider", "unknown"),
                "model": model_name,
                "status": t.get("status", "success"),
                "latency_ms": round(lat_ms, 1),
                "ttft_ms": None,
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "total_tokens": t_tok,
                "tokens_per_sec": tps,
                "cost_usd": round(float(cost), 6),
                "fallback_used": bool(t.get("fallback_used", False)),
                "is_cached": bool(t.get("is_cached", False)),
                "error": t.get("error"),
            })
    return items


@router.get("/api/v1/traces")
async def get_request_traces(limit: int = Query(50, ge=1, le=500), _: str = Depends(auth)):
    """Return recent request execution traces with latency, TPS, token usage, and fallback flags."""
    traces = await _collect_recent_traces(limit=limit)
    return {"traces": traces, "total": len(traces)}


@router.get("/api/v1/traces/otel")
async def export_otel_traces(limit: int = Query(50, ge=1, le=500), _: str = Depends(auth)):
    """Export recent request traces in OpenTelemetry OTLP-compatible JSON resourceSpans format."""
    traces = await _collect_recent_traces(limit=limit)
    spans = []
    for idx, t in enumerate(traces):
        start_ns = int(float(t.get("created_at") or 0) * 1_000_000_000)
        dur_ns = int(float(t.get("latency_ms") or 0) * 1_000_000)
        spans.append({
            "traceId": f"{abs(hash(str(t.get('id', idx)))):032x}"[:32],
            "spanId": f"{idx + 1:016x}",
            "name": f"llm.chat.completions ({t.get('model')})",
            "kind": "SPAN_KIND_CLIENT",
            "startTimeUnixNano": str(start_ns),
            "endTimeUnixNano": str(start_ns + dur_ns),
            "status": {
                "code": "STATUS_CODE_OK" if t.get("status") in ("success", "fallback") else "STATUS_CODE_ERROR"
            },
            "attributes": [
                {"key": "gen_ai.system", "value": {"stringValue": str(t.get("provider", "unknown"))}},
                {"key": "gen_ai.request.model", "value": {"stringValue": str(t.get("model", "unknown"))}},
                {"key": "gen_ai.usage.input_tokens", "value": {"intValue": int(t.get("prompt_tokens", 0))}},
                {"key": "gen_ai.usage.output_tokens", "value": {"intValue": int(t.get("completion_tokens", 0))}},
                {"key": "veloroute.tokens_per_sec", "value": {"doubleValue": float(t.get("tokens_per_sec", 0.0))}},
                {"key": "veloroute.cost_usd", "value": {"doubleValue": float(t.get("cost_usd", 0.0))}},
                {"key": "veloroute.fallback_used", "value": {"boolValue": bool(t.get("fallback_used", False))}},
            ],
        })
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "veloroute-gateway"}},
                        {"key": "service.version", "value": {"stringValue": "2.0.0"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "veloroute.observability.tracer"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }



