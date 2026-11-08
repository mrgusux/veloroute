"""
Anthropic Messages API Protocol Adapter
=======================================
Implements /v1/messages conforming to the Anthropic Messages API specification.
Translates Anthropic requests into VeloRoute completions and streams Anthropic SSE events.
Inspired by LiteLLM, One-API, Relay, and Simple One API.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .deps import llm_client
from .routing import (
    _RUNTIME_CANARY,
    _RUNTIME_SHADOW,
    _GLOBAL_GUARDRAIL_CONFIG,
    record_shadow_execution,
    record_security_audit,
)
from veloroute.schema import Message
from veloroute.gateway.keys import GatewayAuthError

router = APIRouter()


class AnthropicMessageItem(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]


class AnthropicMessagesRequest(BaseModel):
    model: str
    messages: List[AnthropicMessageItem]
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    max_tokens: int = 1024
    temperature: Optional[float] = 1.0
    stream: Optional[bool] = False
    stop_sequences: Optional[List[str]] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    display_model: Optional[str] = None


def _format_content_to_text(content: Union[str, List[Dict[str, Any]]]) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif item.get("type") == "image":
                parts.append("[Image]")
    return "\n".join(parts)


@router.post("/v1/messages")
async def anthropic_messages_endpoint(
    req: AnthropicMessagesRequest,
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
    authorization: Optional[str] = Header(None),
):
    # 1. Authorize via virtual key if enforced
    bearer_token = x_api_key
    if not bearer_token and authorization and authorization.startswith("Bearer "):
        bearer_token = authorization.split("Bearer ", 1)[1].strip()

    reservation_id = None
    authorized_key = None
    queue_timeout = 0.0
    qt_hdr = request.headers.get("x-ratelimit-queue-timeout")
    if qt_hdr:
        try:
            queue_timeout = max(0.0, min(60.0, float(qt_hdr)))
        except ValueError:
            pass

    if llm_client.virtual_keys.enforcement_enabled:
        if not bearer_token:
            raise HTTPException(
                status_code=401,
                detail={"type": "error", "error": {"type": "authentication_error", "message": "x-api-key or Bearer token required"}},
            )
        try:
            authorized_key, reservation_id = await llm_client.virtual_keys.authorize_with_reservation(
                bearer_token,
                model=req.model,
                estimated_tokens=req.max_tokens,
                queue_timeout=queue_timeout,
            )
        except GatewayAuthError as gae:
            raise HTTPException(
                status_code=gae.status_code,
                detail={"type": "error", "error": {"type": gae.code, "message": gae.message}},
            )

    # 2. Convert Anthropic messages to VeloRoute messages
    cycle_messages: List[Message] = []
    if req.system:
        system_text = _format_content_to_text(req.system)
        cycle_messages.append(Message(role="system", content=system_text))

    for m in req.messages:
        text = _format_content_to_text(m.content)
        cycle_messages.append(Message(role=m.role, content=text))

    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    trace_id = request.headers.get("x-trace-id") or msg_id
    display_model = req.display_model or req.model
    active_model = req.model

    # 2a. Canary Traffic Splitting
    if _RUNTIME_CANARY.get("enabled"):
        c_prim = _RUNTIME_CANARY.get("primary_model", "")
        if not c_prim or c_prim == req.model:
            c_model = _RUNTIME_CANARY.get("canary_model")
            c_weight = float(_RUNTIME_CANARY.get("canary_weight", 0) or 0)
            if c_model and 0 < c_weight <= 100 and secrets.randbelow(100) < c_weight:
                active_model = c_model

    # 2b. Shadow Target
    shadow_model = request.headers.get("x-shadow-model")
    if not shadow_model and _RUNTIME_SHADOW.get("enabled"):
        s_prim = _RUNTIME_SHADOW.get("primary_model", "")
        if not s_prim or s_prim == req.model:
            shadow_model = _RUNTIME_SHADOW.get("shadow_model")

    # 2c. Prompt Injection Shield
    req_inj = (
        request.headers.get("x-injection-protection", "").lower() in ("true", "1")
        or bool(_GLOBAL_GUARDRAIL_CONFIG.get("injection_protection", False))
    )
    if req_inj:
        from veloroute.core.injection import InjectionGuard
        full_prompt = "\n".join(m.content for m in cycle_messages if m.content)
        inj_thresh = float(_GLOBAL_GUARDRAIL_CONFIG.get("injection_threshold", 0.7) or 0.7)
        inj_res = InjectionGuard(threshold=inj_thresh).scan(full_prompt)
        if inj_res.blocked:
            record_security_audit(
                event_type="prompt_injection",
                action="blocked",
                score=inj_res.score,
                matches=inj_res.matches,
                model=active_model,
                trace_id=trace_id,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": f"Prompt injection detected (score={inj_res.score}): {', '.join(inj_res.matches)}",
                    },
                },
            )

    # 2d. PII Guardrail
    guardrail_mode = (request.headers.get("x-guardrail-mode") or "off").lower().strip()
    if guardrail_mode == "off" and _GLOBAL_GUARDRAIL_CONFIG.get("pii_mode", "off") != "off":
        guardrail_mode = str(_GLOBAL_GUARDRAIL_CONFIG.get("pii_mode", "off")).lower().strip()

    g_mgr = None
    if guardrail_mode in ("redact", "mask"):
        from veloroute.core.guardrail import GuardrailManager
        g_mgr = GuardrailManager()
        for m in cycle_messages:
            if m.content:
                m.content = g_mgr.mask_prompt(m.content)
        if g_mgr.counter > 0:
            record_security_audit(
                event_type="pii_detection",
                action="sanitized",
                pii_count=g_mgr.counter,
                model=active_model,
                trace_id=trace_id,
            )
    elif guardrail_mode == "block":
        from veloroute.core.guardrail import GuardrailManager
        test_mgr = GuardrailManager()
        for m in cycle_messages:
            if m.content:
                test_mgr.mask_prompt(m.content)
        if test_mgr.counter > 0:
            record_security_audit(
                event_type="pii_detection",
                action="blocked",
                pii_count=test_mgr.counter,
                model=active_model,
                trace_id=trace_id,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": f"PII or sensitive secret detected ({test_mgr.counter} instances). Request rejected by guardrail policy.",
                    },
                },
            )

    # 3. Handle Streaming
    if req.stream:
        async def anthropic_sse_stream() -> AsyncGenerator[str, None]:
            input_tokens = len(" ".join(m.content for m in cycle_messages).split())
            output_text = []

            # Event 1: message_start
            start_payload = {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "model": display_model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": input_tokens, "output_tokens": 1},
                },
            }
            yield f"event: message_start\ndata: {json.dumps(start_payload)}\n\n"

            # Event 2: content_block_start
            block_start = {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }
            yield f"event: content_block_start\ndata: {json.dumps(block_start)}\n\n"

            try:
                stream_iter = llm_client.stream(
                    active_model,
                    messages=cycle_messages,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                )
                async for chunk in stream_iter:
                    delta_text = chunk if isinstance(chunk, str) else (getattr(chunk, "content", "") or "")
                    if delta_text:
                        output_text.append(delta_text)
                        delta_payload = {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": delta_text},
                        }
                        yield f"event: content_block_delta\ndata: {json.dumps(delta_payload)}\n\n"

                # Event 3: content_block_stop
                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"

                # Event 4: message_delta
                out_tokens = len(" ".join(output_text).split())
                msg_delta = {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": max(1, out_tokens)},
                }
                yield f"event: message_delta\ndata: {json.dumps(msg_delta)}\n\n"

                # Event 5: message_stop
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

                # Record virtual key usage
                if authorized_key and reservation_id:
                    await llm_client.virtual_keys.record_usage(
                        authorized_key.id,
                        prompt_tokens=input_tokens,
                        completion_tokens=max(1, out_tokens),
                        reserved_tokens=req.max_tokens,
                        reservation_id=reservation_id,
                    )
            except Exception as e:
                err_payload = {
                    "type": "error",
                    "error": {"type": "api_error", "message": str(e)},
                }
                yield f"event: error\ndata: {json.dumps(err_payload)}\n\n"

        return StreamingResponse(
            anthropic_sse_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # 4. Handle Non-Streaming
    try:
        resp = await llm_client.complete(
            active_model,
            messages=cycle_messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"type": "error", "error": {"type": "api_error", "message": str(exc)}},
        ) from exc

    resp_text = resp.content or ""
    if g_mgr and g_mgr.counter > 0 and isinstance(resp_text, str):
        resp_text = g_mgr.unmask_response(resp_text)

    if shadow_model:
        async def _run_anth_shadow():
            sh_t0 = time.monotonic()
            try:
                sh_resp = await llm_client.complete(
                    shadow_model,
                    messages=cycle_messages,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                )
                sh_lat = round((time.monotonic() - sh_t0) * 1000, 1)
                record_shadow_execution(
                    trace_id=trace_id,
                    primary_model=resp.model,
                    shadow_model=shadow_model,
                    primary_latency_ms=round(getattr(resp, "latency_ms", 0.0) or 0.0, 1),
                    shadow_latency_ms=sh_lat,
                    primary_tokens=(getattr(resp, "prompt_tokens", 0) or 0) + (getattr(resp, "completion_tokens", 0) or 0),
                    shadow_tokens=(getattr(sh_resp, "prompt_tokens", 0) or 0) + (getattr(sh_resp, "completion_tokens", 0) or 0),
                    status="success",
                    shadow_preview=str(sh_resp.content or "")[:160],
                )
            except Exception as sh_err:
                sh_lat = round((time.monotonic() - sh_t0) * 1000, 1)
                record_shadow_execution(
                    trace_id=trace_id,
                    primary_model=resp.model,
                    shadow_model=shadow_model,
                    primary_latency_ms=round(getattr(resp, "latency_ms", 0.0) or 0.0, 1),
                    shadow_latency_ms=sh_lat,
                    primary_tokens=(getattr(resp, "prompt_tokens", 0) or 0) + (getattr(resp, "completion_tokens", 0) or 0),
                    shadow_tokens=0,
                    status="error",
                    error=str(sh_err),
                )
        asyncio.create_task(_run_anth_shadow())

    in_tokens = getattr(resp, "prompt_tokens", 0) or 0
    out_tokens = getattr(resp, "completion_tokens", 0) or 0

    if authorized_key and reservation_id:
        cost = getattr(resp, "cost_usd", None)
        if cost is None:
            cost = llm_client._estimate_cost(active_model, in_tokens, out_tokens) or 0.0
        await llm_client.virtual_keys.record_usage(
            authorized_key.id,
            prompt_tokens=in_tokens,
            completion_tokens=out_tokens,
            cost_usd=cost,
            reserved_tokens=req.max_tokens,
            reservation_id=reservation_id,
        )

    anthropic_resp = {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": display_model,
        "content": [
            {
                "type": "text",
                "text": resp_text,
            }
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
        },
    }
    return JSONResponse(anthropic_resp)


@router.post("/p/{provider}/v1/messages")
@router.post("/p/{provider}/messages")
async def provider_anthropic_messages_endpoint(
    provider: str,
    req: AnthropicMessagesRequest,
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
    authorization: Optional[str] = Header(None),
):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(
            status_code=404,
            detail={"type": "error", "error": {"type": "not_found", "message": f"Provider '{provider}' not found or not configured"}},
        )
    orig_model = req.model
    m_str = req.model.strip()
    if "/" in m_str:
        prefix, rest = m_str.split("/", 1)
        if prefix.lower() == p_lower:
            req.model = m_str
        elif prefix.lower() in llm_client.get_providers():
            req.model = f"{p_lower}/{rest}"
        else:
            req.model = f"{p_lower}/{m_str}"
    else:
        req.model = f"{p_lower}/{m_str}"
    req.display_model = orig_model
    return await anthropic_messages_endpoint(req, request, x_api_key, authorization)
