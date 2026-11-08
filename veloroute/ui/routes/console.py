import asyncio
import secrets
import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from .deps import auth, llm_client
from .models import TestCompleteRequest
from .routing import (
    _RUNTIME_CANARY,
    _RUNTIME_SHADOW,
    _GLOBAL_GUARDRAIL_CONFIG,
    record_shadow_execution,
    record_security_audit,
)
from veloroute.core.injection import InjectionGuard
from veloroute.core.guardrail import GuardrailManager

router = APIRouter()

@router.post("/api/v1/complete")
async def test_complete(req: TestCompleteRequest, _: str = Depends(auth)):
    trace_id = f"trace-console-{secrets.token_hex(6)}"
    active_model = req.model
    is_canary = False

    # 1. Canary Traffic Splitting (request override or global runtime config)
    canary_model = req.canary_model
    canary_weight = req.canary_weight
    if not canary_model and _RUNTIME_CANARY.get("enabled"):
        prim = _RUNTIME_CANARY.get("primary_model", "")
        if not prim or prim == req.model:
            canary_model = _RUNTIME_CANARY.get("canary_model")
            canary_weight = _RUNTIME_CANARY.get("canary_weight", 0)

    if canary_model and canary_weight is not None:
        try:
            if 0 < float(canary_weight) <= 100 and secrets.randbelow(100) < float(canary_weight):
                active_model = canary_model
                is_canary = True
        except Exception:
            pass

    # 2. Prompt Injection Shield (request override or global security policy)
    inj_score = 0.0
    use_inj = bool(req.injection_protection or _GLOBAL_GUARDRAIL_CONFIG.get("injection_protection"))
    if use_inj:
        thresh = float(_GLOBAL_GUARDRAIL_CONFIG.get("injection_threshold", 0.7) or 0.7)
        guard = InjectionGuard(threshold=thresh)
        res = guard.scan(req.prompt)
        inj_score = res.score
        if res.blocked:
            record_security_audit(
                event_type="prompt_injection",
                action="blocked",
                score=res.score,
                matches=res.matches,
                model=active_model,
                trace_id=trace_id,
            )
            return {
                "content": f"[BLOCKED BY INJECTION SHIELD] Score: {res.score}. Attack patterns: {', '.join(res.matches)}",
                "error": True,
                "provider": "gateway_guardrail",
                "model": active_model,
                "latency_ms": 0.5,
                "guardrail_status": "blocked",
                "injection_score": inj_score,
                "pii_masked": 0,
                "canary_used": is_canary,
                "trace_id": trace_id,
                "tokens": {"prompt": 0, "completion": 0},
                "cost_usd": "0.000000",
            }

    # 3. PII Guardrail (request override or global security policy)
    prompt_to_send = req.prompt
    g_mgr = None
    g_mode = (req.guardrail_mode or "off").lower()
    if g_mode == "off" and _GLOBAL_GUARDRAIL_CONFIG.get("pii_mode", "off") != "off":
        g_mode = str(_GLOBAL_GUARDRAIL_CONFIG.get("pii_mode", "off")).lower()

    if g_mode in ("redact", "mask"):
        g_mgr = GuardrailManager()
        prompt_to_send = g_mgr.mask_prompt(req.prompt)
        if g_mgr.counter > 0:
            record_security_audit(
                event_type="pii_detection",
                action="sanitized",
                pii_count=g_mgr.counter,
                model=active_model,
                trace_id=trace_id,
            )
    elif g_mode == "block":
        test_mgr = GuardrailManager()
        test_mgr.mask_prompt(req.prompt)
        if test_mgr.counter > 0:
            record_security_audit(
                event_type="pii_detection",
                action="blocked",
                pii_count=test_mgr.counter,
                model=active_model,
                trace_id=trace_id,
            )
            return {
                "content": f"[BLOCKED BY PII POLICY] Detected {test_mgr.counter} sensitive PII entity instances. Request rejected.",
                "error": True,
                "provider": "gateway_guardrail",
                "model": active_model,
                "latency_ms": 0.5,
                "guardrail_status": "blocked",
                "injection_score": inj_score,
                "pii_masked": test_mgr.counter,
                "canary_used": is_canary,
                "trace_id": trace_id,
                "tokens": {"prompt": 0, "completion": 0},
                "cost_usd": "0.000000",
            }

    shadow_target = req.shadow_model
    if not shadow_target and _RUNTIME_SHADOW.get("enabled"):
        s_prim = _RUNTIME_SHADOW.get("primary_model", "")
        if not s_prim or s_prim == req.model:
            shadow_target = _RUNTIME_SHADOW.get("shadow_model")

    try:
        resp = await llm_client.complete(
            model=active_model,
            prompt=prompt_to_send,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            max_retries=req.max_retries,
            retry_delay=req.retry_delay,
        )

        content = resp.content
        if g_mgr and g_mgr.counter > 0 and isinstance(content, str):
            content = g_mgr.unmask_response(content)

        # 4. Shadow Target Execution (asynchronous)
        if shadow_target:
            async def _run_shadow():
                sh_t0 = time.monotonic()
                try:
                    sh_resp = await llm_client.complete(
                        model=shadow_target,
                        prompt=prompt_to_send,
                        temperature=req.temperature,
                        max_tokens=req.max_tokens,
                    )
                    sh_lat = round((time.monotonic() - sh_t0) * 1000, 1)
                    record_shadow_execution(
                        trace_id=trace_id,
                        primary_model=resp.model,
                        shadow_model=shadow_target,
                        primary_latency_ms=round(resp.latency_ms, 1),
                        shadow_latency_ms=sh_lat,
                        primary_tokens=(resp.prompt_tokens or 0) + (resp.completion_tokens or 0),
                        shadow_tokens=(sh_resp.prompt_tokens or 0) + (sh_resp.completion_tokens or 0),
                        status="success",
                        shadow_preview=str(sh_resp.content or "")[:160],
                    )
                except Exception as sh_err:
                    sh_lat = round((time.monotonic() - sh_t0) * 1000, 1)
                    record_shadow_execution(
                        trace_id=trace_id,
                        primary_model=resp.model,
                        shadow_model=shadow_target,
                        primary_latency_ms=round(resp.latency_ms, 1),
                        shadow_latency_ms=sh_lat,
                        primary_tokens=(resp.prompt_tokens or 0) + (resp.completion_tokens or 0),
                        shadow_tokens=0,
                        status="error",
                        error=str(sh_err),
                    )
            asyncio.create_task(_run_shadow())

        cost_val = llm_client._estimate_cost(
            active_model,
            getattr(resp, "prompt_tokens", 0) or 0,
            getattr(resp, "completion_tokens", 0) or 0,
        ) or 0.0

        guard_status = "sanitized" if (g_mgr and g_mgr.counter > 0) else ("passed" if g_mode != "off" else "off")

        return {
            "content": content,
            "provider": resp.provider,
            "model": resp.model,
            "latency_ms": round(resp.latency_ms, 1),
            "tokens": {"prompt": resp.prompt_tokens, "completion": resp.completion_tokens},
            "cost_usd": f"{cost_val:.6f}",
            "guardrail_status": guard_status,
            "pii_masked": g_mgr.counter if g_mgr else 0,
            "injection_score": inj_score,
            "canary_used": is_canary,
            "shadow_target": shadow_target if shadow_target else None,
            "trace_id": trace_id,
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/api/v1/stream")
async def test_stream(
    model: str = Query(...),
    prompt: str = Query(...),
    max_retries: int = Query(2),
    retry_delay: float = Query(1.0),
    _: str = Depends(auth),
):
    async def event_generator():
        try:
            async for chunk in llm_client.stream(
                model=model,
                prompt=prompt,
                max_retries=max_retries,
                retry_delay=retry_delay,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {e}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class ComparatorRequest(BaseModel):
    model_a: str
    model_b: str
    prompt: str
    system_prompt: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512


@router.post("/api/v1/comparator/run")
async def run_comparator(req: ComparatorRequest, _: str = Depends(auth)):
    if not req.model_a or not req.model_b:
        raise HTTPException(400, "Both model_a and model_b are required")
    if not req.prompt:
        raise HTTPException(400, "Prompt is required")

    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.append({"role": "user", "content": req.prompt})

    async def execute_model(model_name: str) -> Dict[str, Any]:
        t0 = time.monotonic()
        try:
            resp = await llm_client.complete(
                model=model_name,
                messages=messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            )
            lat_ms = round((time.monotonic() - t0) * 1000, 1)
            prompt_tok = getattr(resp, "prompt_tokens", 0) or 0
            comp_tok = getattr(resp, "completion_tokens", 0) or 0
            cost_val = llm_client._estimate_cost(model_name, prompt_tok, comp_tok) or 0.0
            tok_per_sec = (
                round(comp_tok / (lat_ms / 1000.0), 1)
                if lat_ms > 0 and comp_tok > 0
                else 0.0
            )

            return {
                "model": model_name,
                "provider": getattr(resp, "provider", "unknown"),
                "content": resp.content,
                "latency_ms": lat_ms,
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "total_tokens": prompt_tok + comp_tok,
                "cost_usd": f"{cost_val:.6f}",
                "tokens_per_sec": tok_per_sec,
                "status": "success",
            }
        except Exception as e:
            lat_ms = round((time.monotonic() - t0) * 1000, 1)
            return {
                "model": model_name,
                "content": f"Error: {e}",
                "latency_ms": lat_ms,
                "status": "error",
            }

    res_a, res_b = await asyncio.gather(
        execute_model(req.model_a),
        execute_model(req.model_b),
        return_exceptions=False,
    )

    speed_winner = None
    cost_winner = None
    if res_a.get("status") == "success" and res_b.get("status") == "success":
        lat_a = res_a["latency_ms"]
        lat_b = res_b["latency_ms"]
        if lat_a < lat_b:
            speed_pct = round(((lat_b - lat_a) / lat_b) * 100, 1) if lat_b > 0 else 0
            speed_winner = {"winner": "a", "model": req.model_a, "pct_faster": speed_pct}
        elif lat_b < lat_a:
            speed_pct = round(((lat_a - lat_b) / lat_a) * 100, 1) if lat_a > 0 else 0
            speed_winner = {"winner": "b", "model": req.model_b, "pct_faster": speed_pct}

        cost_a = float(res_a["cost_usd"])
        cost_b = float(res_b["cost_usd"])
        if cost_a < cost_b:
            cost_pct = round(((cost_b - cost_a) / cost_b) * 100, 1) if cost_b > 0 else 0
            cost_winner = {"winner": "a", "model": req.model_a, "pct_cheaper": cost_pct}
        elif cost_b < cost_a:
            cost_pct = round(((cost_a - cost_b) / cost_a) * 100, 1) if cost_a > 0 else 0
            cost_winner = {"winner": "b", "model": req.model_b, "pct_cheaper": cost_pct}

    return {
        "model_a": res_a,
        "model_b": res_b,
        "speed_winner": speed_winner,
        "cost_winner": cost_winner,
    }

