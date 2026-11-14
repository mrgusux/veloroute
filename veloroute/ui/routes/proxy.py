"""OpenAI-compatible inference endpoints exposed by the local gateway."""
from __future__ import annotations

import asyncio
import fnmatch
import json
import secrets
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .deps import llm_client
from .routing import (
    _RUNTIME_CANARY,
    _RUNTIME_SHADOW,
    _GLOBAL_GUARDRAIL_CONFIG,
    record_shadow_execution,
    record_security_audit,
)
from veloroute.core.errors import APIConnectionError, AllProvidersFailedError
from veloroute.gateway.keys import GatewayAuthError, VirtualKey
from veloroute.utils import count_message_tokens, count_tokens, extract_forward_headers

router = APIRouter()


def _proxy_error_response(exc: Exception) -> JSONResponse:
    """Preserve upstream HTTP semantics in the OpenAI-compatible error body."""
    cause = exc
    if isinstance(exc, AllProvidersFailedError) and exc.errors:
        cause = exc.errors[-1]

    status_code = getattr(cause, "status_code", 0)
    if not isinstance(status_code, int) or not 400 <= status_code <= 599:
        status_code = 502 if isinstance(cause, APIConnectionError) else 500

    error_type = type(cause).__name__
    message = getattr(exc, "detail", None) or str(exc)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "code": error_type,
            }
        },
    )


def _request_api_key(request: Request) -> Optional[str]:
    authorization = request.headers.get("authorization", "")
    scheme, separator, value = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return request.headers.get("x-api-key") or request.headers.get("api-key")


async def _authorize_gateway_request(
    request: Request,
    *,
    model: str = "",
    estimated_tokens: int = 0,
    check_model: bool = True,
    budget_pricing_available: Optional[bool] = None,
) -> tuple[Optional[VirtualKey], Optional[str]]:
    manager = llm_client.virtual_keys
    if not manager.enforcement_enabled:
        return None, None

    queue_timeout = 0.0
    qt_hdr = request.headers.get("x-ratelimit-queue-timeout")
    if qt_hdr:
        try:
            queue_timeout = max(0.0, min(60.0, float(qt_hdr)))
        except ValueError:
            pass

    try:
        record, reservation_id = await manager.authorize_with_reservation(
            _request_api_key(request),
            model=model,
            resolved_model=llm_client._resolve_model(model) if model else None,
            estimated_tokens=estimated_tokens,
            check_model=check_model,
            budget_pricing_available=(
                budget_pricing_available
                if budget_pricing_available is not None
                else (
                    not model
                    or llm_client._get_pricing(llm_client._resolve_model(model)) is not None
                )
            ),
            queue_timeout=queue_timeout,
        )
    except GatewayAuthError:
        llm_client.metrics.inc_counter(
            "veloroute_gateway_requests_total", {"result": "denied"}
        )
        raise
    llm_client.metrics.inc_counter(
        "veloroute_gateway_requests_total", {"result": "authorized"}
    )
    return record, reservation_id


async def _record_gateway_usage(
    record: Optional[VirtualKey],
    reservation_id: Optional[str],
    *,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_tokens: int = 0,
    count_estimate_when_missing: bool = True,
) -> None:
    if record is None:
        return
    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    if (
        count_estimate_when_missing
        and prompt_tokens + completion_tokens == 0
        and estimated_tokens
    ):
        # Retain a conservative charge when the provider omits usage metadata.
        prompt_tokens = estimated_tokens
    cost = llm_client._estimate_cost(model, prompt_tokens, completion_tokens) or 0.0
    await llm_client.virtual_keys.record_usage(
        record.id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
        reserved_tokens=estimated_tokens,
        reservation_id=reservation_id,
        count_estimate_when_missing=count_estimate_when_missing,
    )
    llm_client.metrics.inc_counter(
        "veloroute_gateway_requests_total", {"result": "completed"}
    )


def _safe_message_token_estimate(messages: Any, model: str) -> int:
    try:
        return max(0, count_message_tokens(messages or [], model=model))
    except (TypeError, ValueError, AttributeError):
        return 0


def _key_can_access_model(record: VirtualKey, model_id: str, root: str = "") -> bool:
    candidates = [model_id, root]
    if "/" in model_id:
        candidates.append(model_id.split("/", 1)[1])
    return not record.allowed_models or any(
        fnmatch.fnmatchcase(candidate, pattern)
        for candidate in candidates
        if candidate
        for pattern in record.allowed_models
    )


@router.post("/v1/chat/completions")
async def openai_proxy_chat_completions(req: Dict[str, Any], request: Request):
    model = req.get("model")
    if not model:
        raise HTTPException(400, "Missing 'model' field")
    if hasattr(llm_client, "transforms"):
        model = llm_client.transforms.transform_model(model)
    display_model = req.get("display_model") or model

    messages = req.get("messages", [])
    prompt_tokens_est = _safe_message_token_estimate(messages, model)
    gateway_key, reservation_id = await _authorize_gateway_request(
        request, model=model, estimated_tokens=prompt_tokens_est
    )
    stream = req.get("stream", False)
    forward_headers = extract_forward_headers(dict(request.headers))
    if hasattr(llm_client, "transforms"):
        forward_headers = llm_client.transforms.transform_request_headers(forward_headers)

    # ─── Extract Tracing & Request Metadata ───────────────────────────────────
    req_headers = dict(request.headers)
    trace_id = (
        req_headers.get("x-trace-id")
        or req_headers.get("x-request-id")
        or req_headers.get("x-correlation-id")
        or f"trace-{secrets.token_hex(12)}"
    )
    session_id = req_headers.get("x-session-id")
    user_id = req_headers.get("x-user-id")
    team_id = req_headers.get("x-team-id")
    workplace_id = req_headers.get("x-workplace-id")
    tags_header = req_headers.get("x-tags")
    tags = [t.strip() for t in tags_header.split(",") if t.strip()] if tags_header else None
    req_privacy = (
        req_headers.get("x-privacy-mode", "").lower() in ("true", "1")
        or bool(getattr(llm_client, "privacy_mode", False))
    )

    # ─── Queued Duration ──────────────────────────────────────────────────────
    queued_ms = llm_client.virtual_keys.pop_queued_ms(reservation_id)

    # ─── Canary Traffic Splitting ─────────────────────────────────────────────
    orig_requested_model = model
    canary_model = req_headers.get("x-canary-model") or req.get("canary_model")
    canary_weight_str = req_headers.get("x-canary-weight") or req.get("canary_weight")
    if not canary_model and _RUNTIME_CANARY.get("enabled"):
        c_prim = _RUNTIME_CANARY.get("primary_model", "")
        if not c_prim or c_prim == orig_requested_model:
            canary_model = _RUNTIME_CANARY.get("canary_model")
            canary_weight_str = str(_RUNTIME_CANARY.get("canary_weight", 0))

    is_canary = False
    if canary_model and canary_weight_str is not None:
        try:
            c_weight = float(canary_weight_str)
            if 0 < c_weight <= 100 and secrets.randbelow(100) < c_weight:
                model = canary_model
                is_canary = True
        except ValueError:
            pass

    # ─── Shadow / Dark Routing Target ─────────────────────────────────────────
    shadow_model = req_headers.get("x-shadow-model") or req.get("shadow_model")
    if not shadow_model and _RUNTIME_SHADOW.get("enabled"):
        s_prim = _RUNTIME_SHADOW.get("primary_model", "")
        if not s_prim or s_prim == orig_requested_model:
            shadow_model = _RUNTIME_SHADOW.get("shadow_model")

    # ─── Prompt Injection Guardrail ───────────────────────────────────────────
    injection_protection = (
        req_headers.get("x-injection-protection", "").lower() in ("true", "1")
        or bool(req.get("injection_protection", False))
        or bool(_GLOBAL_GUARDRAIL_CONFIG.get("injection_protection", False))
    )
    inj_score = 0.0
    if injection_protection:
        from veloroute.core.injection import InjectionGuard
        user_texts = []
        for m in messages:
            if isinstance(m, dict):
                c = m.get("content")
                if isinstance(c, str):
                    user_texts.append(c)
                elif isinstance(c, list):
                    for p in c:
                        if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str):
                            user_texts.append(p.get("text", ""))
        full_prompt = "\n".join(user_texts)
        inj_thresh = float(_GLOBAL_GUARDRAIL_CONFIG.get("injection_threshold", 0.7) or 0.7)
        inj_guard = InjectionGuard(threshold=inj_thresh)
        inj_res = inj_guard.scan(full_prompt)
        inj_score = inj_res.score
        if inj_res.blocked:
            record_security_audit(
                event_type="prompt_injection",
                action="blocked",
                score=inj_res.score,
                matches=inj_res.matches,
                model=model,
                trace_id=trace_id,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": f"Prompt injection detected (score={inj_res.score}): {', '.join(inj_res.matches)}",
                        "type": "guardrail_violation",
                        "code": "prompt_injection_blocked",
                    }
                },
                headers={
                    "X-Guardrail-Status": "blocked",
                    "X-Guardrail-Injection-Score": str(inj_res.score),
                    "X-Trace-Id": trace_id,
                },
            )

    # ─── PII & Secret Guardrail Scrubber ──────────────────────────────────────
    guardrail_mode = (
        req_headers.get("x-guardrail-mode")
        or req.get("guardrail_mode")
        or "off"
    ).lower().strip()
    if guardrail_mode == "off" and _GLOBAL_GUARDRAIL_CONFIG.get("pii_mode", "off") != "off":
        guardrail_mode = str(_GLOBAL_GUARDRAIL_CONFIG.get("pii_mode", "off")).lower().strip()

    g_mgr = None
    if guardrail_mode in ("redact", "mask"):
        from veloroute.core.guardrail import GuardrailManager
        g_mgr = GuardrailManager()
        for m in messages:
            if isinstance(m, dict):
                c = m.get("content")
                if isinstance(c, str):
                    m["content"] = g_mgr.mask_prompt(c)
                elif isinstance(c, list):
                    for p in c:
                        if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str):
                            p["text"] = g_mgr.mask_prompt(p["text"])
        if g_mgr.counter > 0:
            record_security_audit(
                event_type="pii_detection",
                action="sanitized",
                pii_count=g_mgr.counter,
                model=model,
                trace_id=trace_id,
            )
    elif guardrail_mode == "block":
        from veloroute.core.guardrail import GuardrailManager
        test_mgr = GuardrailManager()
        user_texts = [m.get("content", "") for m in messages if isinstance(m, dict) and isinstance(m.get("content"), str)]
        for t in user_texts:
            test_mgr.mask_prompt(t)
        if test_mgr.counter > 0:
            record_security_audit(
                event_type="pii_detection",
                action="blocked",
                pii_count=test_mgr.counter,
                model=model,
                trace_id=trace_id,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": f"PII or sensitive secret detected ({test_mgr.counter} instances). Request rejected by guardrail policy.",
                        "type": "guardrail_violation",
                        "code": "pii_detected_blocked",
                    }
                },
                headers={
                    "X-Guardrail-Status": "blocked",
                    "X-Guardrail-PII-Masked": str(test_mgr.counter),
                    "X-Trace-Id": trace_id,
                },
            )

    # Dynamic routing overrides
    req_strategy_name = req_headers.get("x-routing-strategy")
    req_strategy = None
    if req_strategy_name:
        try:
            from veloroute.core.router import RoutingStrategy
            req_strategy = RoutingStrategy(req_strategy_name.lower())
        except Exception:
            pass

    max_retries = None
    if "x-max-retries" in req_headers:
        try:
            max_retries = int(req_headers["x-max-retries"])
        except ValueError:
            pass

    req_timeout = None
    if "x-timeout" in req_headers:
        try:
            req_timeout = float(req_headers["x-timeout"])
        except ValueError:
            pass

    gen_kwargs = {}
    for k in (
        "temperature", "max_tokens", "max_completion_tokens", "top_p",
        "presence_penalty", "frequency_penalty", "stop", "tools",
        "tool_choice", "response_format",
    ):
        if k in req:
            if k == "max_completion_tokens" and "max_tokens" not in req:
                gen_kwargs["max_tokens"] = req[k]
            else:
                gen_kwargs[k] = req[k]

    # ─── Cache Detection & Bypass ─────────────────────────────────────────────
    cache_control = req_headers.get("cache-control", "").lower()
    bypass_cache = req_privacy or "no-cache" in cache_control or "no-store" in cache_control
    cache_requested = (
        not bypass_cache and (
            req_headers.get("x-cache", "").lower() in ("true", "1")
            or req_headers.get("x-helicone-cache-enabled", "").lower() in ("true", "1")
            or req_headers.get("x-portkey-cache", "").lower() in ("true", "1")
            or request.query_params.get("cache", "").lower() in ("true", "1")
            or (getattr(llm_client, "_cache", None) is not None and getattr(llm_client, "cache_ttl", None) is not None and getattr(llm_client, "cache_ttl", 0) > 0)
        )
    )
    cache_ttl = 300.0
    if "x-cache-ttl" in req_headers:
        try:
            cache_ttl = float(req_headers["x-cache-ttl"])
        except ValueError:
            pass
    elif getattr(llm_client, "cache_ttl", None):
        cache_ttl = float(llm_client.cache_ttl)

    # Auto-initialize in-memory cache on gateway if requested
    if cache_requested and getattr(llm_client, "_cache", None) is None:
        from veloroute.core.cache import InMemoryCache
        llm_client._cache = InMemoryCache(max_size=2000)

    # Fast path: Check prompt cache for non-streaming completions
    if cache_requested and not stream and getattr(llm_client, "_cache", None):
        cache_key = llm_client._cache_key(model, messages, gen_kwargs)
        cached_resp = await llm_client._cache_get(cache_key)
        cache_hit_type = "exact" if cached_resp else None

        if not cached_resp and getattr(llm_client, "_semantic_cache", None):
            user_texts = [
                m.get("content", "") for m in messages
                if isinstance(m, dict) and m.get("role") == "user"
            ]
            query_text = " ".join(user_texts).strip()
            if query_text:
                cached_resp = await llm_client._semantic_cache.get(query_text, model=model)
                if cached_resp:
                    cache_hit_type = "semantic"

        if cached_resp:
            llm_client.metrics.inc_cache_hit(cache_hit_type or "exact")
            prompt_tokens = cached_resp.prompt_tokens or prompt_tokens_est
            completion_tokens = cached_resp.completion_tokens or 0
            await _record_gateway_usage(
                gateway_key,
                reservation_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_tokens=prompt_tokens_est,
            )
            msg_dict = {"role": "assistant", "content": cached_resp.content}
            if getattr(cached_resp, "reasoning_content", None):
                msg_dict["reasoning_content"] = cached_resp.reasoning_content
            if getattr(cached_resp, "tool_calls", None):
                msg_dict["tool_calls"] = cached_resp.tool_calls
            finish_reason = "tool_calls" if getattr(cached_resp, "tool_calls", None) else "stop"

            resp_payload = {
                "id": cached_resp.id or f"chatcmpl-cached-{secrets.token_hex(8)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": display_model or cached_resp.model,
                "choices": [{"index": 0, "message": msg_dict, "finish_reason": finish_reason}],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
            if g_mgr and g_mgr.counter > 0 and isinstance(msg_dict.get("content"), str):
                msg_dict["content"] = g_mgr.unmask_response(msg_dict["content"])

            resp_headers = {
                "X-Cache": "HIT",
                "X-Cache-Type": cache_hit_type or "exact",
                "X-VeloRoute-Cached": "true",
                "X-Trace-Id": trace_id,
                "X-VeloRoute-Provider": cached_resp.provider or "cached",
                "X-VeloRoute-Model": cached_resp.model,
                "X-VeloRoute-Latency-Ms": "0",
                "X-VeloRoute-Cost-USD": "0.0",
                "X-VeloRoute-Retries": "0",
                "X-VeloRoute-Fallback-Used": "false",
            }
            if queued_ms > 0:
                resp_headers["X-RateLimit-Queued-Ms"] = str(queued_ms)
            if is_canary:
                resp_headers["X-VeloRoute-Canary"] = "true"
                resp_headers["X-VeloRoute-Canary-Model"] = model
            if shadow_model:
                resp_headers["X-VeloRoute-Shadow-Target"] = shadow_model
            if g_mgr and g_mgr.counter > 0:
                resp_headers["X-Guardrail-Status"] = "sanitized"
                resp_headers["X-Guardrail-PII-Masked"] = str(g_mgr.counter)
            elif guardrail_mode != "off":
                resp_headers["X-Guardrail-Status"] = "passed"
            if injection_protection:
                resp_headers["X-Guardrail-Injection-Score"] = str(inj_score)
            return JSONResponse(content=resp_payload, headers=resp_headers)

    if stream:
        async def event_generator():
            completion_tokens_est = 0
            producer_task = None
            chunk_id = f"chatcmpl-{secrets.token_hex(12)}"
            created_ts = int(time.time())
            include_usage = req.get("stream_options", {}).get("include_usage", False)
            queue: asyncio.Queue = asyncio.Queue()
            accumulated_text = ""
            ttft_ms = None
            stream_start_time = time.monotonic()

            async def stream_producer():
                try:
                    stream_kwargs = dict(gen_kwargs)
                    if req_strategy:
                        stream_kwargs["strategy"] = req_strategy
                    if max_retries is not None:
                        stream_kwargs["max_retries"] = max_retries
                    if req_timeout is not None:
                        stream_kwargs["timeout"] = req_timeout

                    async for text in llm_client.stream(
                        model=model,
                        messages=messages,
                        headers=forward_headers,
                        session_id=session_id,
                        user_id=user_id,
                        team_id=team_id,
                        workplace_id=workplace_id,
                        tags=tags,
                        **stream_kwargs,
                    ):
                        await queue.put(("chunk", text))
                    await queue.put(("done", None))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await queue.put(("error", exc))

            try:
                producer_task = asyncio.create_task(stream_producer())
                while True:
                    try:
                        msg_type, val = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        # SSE keep-alive heartbeat prevents intermediary timeouts.
                        yield ": keep-alive\n\n"
                        continue

                    if msg_type == "chunk":
                        if ttft_ms is None:
                            ttft_ms = round((time.monotonic() - stream_start_time) * 1000, 2)
                        accumulated_text += val
                        completion_tokens_est += max(1, len(val) // 4)
                        chunk = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": display_model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": val},
                                "finish_reason": None,
                            }],
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                    elif msg_type == "done":
                        final_chunk = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": display_model,
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        }
                        if include_usage:
                            final_chunk["usage"] = {
                                "prompt_tokens": prompt_tokens_est,
                                "completion_tokens": completion_tokens_est,
                                "total_tokens": prompt_tokens_est + completion_tokens_est,
                            }
                        yield f"data: {json.dumps(final_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        # If cache requested, store in exact + semantic cache
                        if cache_requested and accumulated_text and not bypass_cache:
                            from veloroute.schema import CompletionResponse
                            c_resp = CompletionResponse(
                                id=chunk_id,
                                model=model,
                                provider="cached",
                                content=accumulated_text,
                                prompt_tokens=prompt_tokens_est,
                                completion_tokens=completion_tokens_est,
                                latency_ms=round((time.monotonic() - stream_start_time) * 1000, 2),
                            )
                            if getattr(llm_client, "_cache", None):
                                c_key = llm_client._cache_key(model, messages, gen_kwargs)
                                await llm_client._cache_set(c_key, c_resp, ttl=cache_ttl)
                            if getattr(llm_client, "_semantic_cache", None):
                                user_texts = [
                                    m.get("content", "") for m in messages
                                    if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)
                                ]
                                query_text = " ".join(user_texts).strip()
                                if query_text:
                                    await llm_client._semantic_cache.set(query_text, c_resp, model=model, ttl=cache_ttl)
                        break
                    else:
                        raise val

                await producer_task
            except asyncio.CancelledError:
                # Client disconnected before stream finished (normal in fast SSE consumers)
                return
            except Exception as exc:
                # Once SSE headers have been sent, report failure using the
                # OpenAI error envelope. Never turn an upstream failure into
                # assistant prose that clients may treat as a successful answer.
                error_response = _proxy_error_response(exc)
                try:
                    error_payload = json.loads(error_response.body.decode("utf-8"))
                except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
                    error_payload = {"error": {"message": str(exc), "type": type(exc).__name__}}
                yield f"data: {json.dumps(error_payload)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                if producer_task is not None and not producer_task.done():
                    producer_task.cancel()
                    try:
                        await producer_task
                    except (asyncio.CancelledError, Exception):
                        pass
                if gateway_key is not None:
                    try:
                        await asyncio.shield(_record_gateway_usage(
                            gateway_key,
                            reservation_id,
                            model=model,
                            prompt_tokens=prompt_tokens_est,
                            completion_tokens=completion_tokens_est,
                            estimated_tokens=prompt_tokens_est,
                        ))
                    except Exception:
                        pass

        headers = {
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "X-Accel-Buffering": "no",
            "X-Trace-Id": trace_id,
            "X-Cache": "MISS" if not bypass_cache else "BYPASS",
            "X-VeloRoute-Cached": "false",
        }
        if queued_ms > 0:
            headers["X-RateLimit-Queued-Ms"] = str(queued_ms)
        if is_canary:
            headers["X-VeloRoute-Canary"] = "true"
            headers["X-VeloRoute-Canary-Model"] = model
        if shadow_model:
            headers["X-VeloRoute-Shadow-Target"] = shadow_model
        if g_mgr and g_mgr.counter > 0:
            headers["X-Guardrail-Status"] = "sanitized"
            headers["X-Guardrail-PII-Masked"] = str(g_mgr.counter)
        elif guardrail_mode != "off":
            headers["X-Guardrail-Status"] = "passed"
        if injection_protection:
            headers["X-Guardrail-Injection-Score"] = str(inj_score)
        return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)

    try:
        complete_kwargs = dict(gen_kwargs)
        if req_strategy:
            complete_kwargs["strategy"] = req_strategy
        if max_retries is not None:
            complete_kwargs["max_retries"] = max_retries
        if req_timeout is not None:
            complete_kwargs["timeout"] = req_timeout
        if cache_requested:
            complete_kwargs["cache_ttl"] = cache_ttl

        resp = await llm_client.complete(
            model=model,
            messages=messages,
            headers=forward_headers,
            session_id=session_id,
            user_id=user_id,
            team_id=team_id,
            workplace_id=workplace_id,
            tags=tags,
            **complete_kwargs,
        )
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            estimated_tokens=prompt_tokens_est,
        )
        msg_dict: Dict[str, Any] = {"role": "assistant", "content": resp.content}
        if hasattr(llm_client, "transforms") and isinstance(msg_dict.get("content"), str):
            msg_dict["content"] = llm_client.transforms.transform_response_text(msg_dict["content"])
        if getattr(resp, "reasoning_content", None):
            msg_dict["reasoning_content"] = resp.reasoning_content
        if getattr(resp, "tool_calls", None):
            msg_dict["tool_calls"] = resp.tool_calls
        finish_reason = "tool_calls" if getattr(resp, "tool_calls", None) else "stop"

        # Restore masked PII in the generated response
        if g_mgr and g_mgr.counter > 0 and isinstance(msg_dict.get("content"), str):
            msg_dict["content"] = g_mgr.unmask_response(msg_dict["content"])

        # Asynchronously execute shadow (dark) evaluation request
        if shadow_model:
            async def _run_shadow_job():
                sh_t0 = time.monotonic()
                try:
                    sh_resp = await llm_client.complete(
                        model=shadow_model,
                        messages=messages,
                        headers=forward_headers,
                        **complete_kwargs,
                    )
                    lat = round((time.monotonic() - sh_t0) * 1000, 2)
                    record_shadow_execution(
                        trace_id=trace_id,
                        primary_model=getattr(resp, "model", model) or model,
                        shadow_model=shadow_model,
                        primary_latency_ms=round(getattr(resp, "latency_ms", 0.0) or 0.0, 2),
                        shadow_latency_ms=lat,
                        primary_tokens=(getattr(resp, "prompt_tokens", 0) or 0) + (getattr(resp, "completion_tokens", 0) or 0),
                        shadow_tokens=(getattr(sh_resp, "prompt_tokens", 0) or 0) + (getattr(sh_resp, "completion_tokens", 0) or 0),
                        status="success",
                        shadow_preview=str(sh_resp.content or "")[:160],
                    )
                    import logging
                    logging.getLogger("veloroute.shadow").info(
                        f"[Shadow Routing] target={shadow_model} trace_id={trace_id} "
                        f"latency_ms={lat} prompt_tokens={sh_resp.prompt_tokens} completion_tokens={sh_resp.completion_tokens}"
                    )
                except Exception as sh_err:
                    lat = round((time.monotonic() - sh_t0) * 1000, 2)
                    record_shadow_execution(
                        trace_id=trace_id,
                        primary_model=getattr(resp, "model", model) or model,
                        shadow_model=shadow_model,
                        primary_latency_ms=round(getattr(resp, "latency_ms", 0.0) or 0.0, 2),
                        shadow_latency_ms=lat,
                        primary_tokens=(getattr(resp, "prompt_tokens", 0) or 0) + (getattr(resp, "completion_tokens", 0) or 0),
                        shadow_tokens=0,
                        status="error",
                        error=str(sh_err),
                    )
                    import logging
                    logging.getLogger("veloroute.shadow").warning(
                        f"[Shadow Routing] target={shadow_model} trace_id={trace_id} failed: {sh_err}"
                    )

            asyncio.create_task(_run_shadow_job())

        if cache_requested and resp and not bypass_cache:
            if getattr(llm_client, "_cache", None):
                c_key = llm_client._cache_key(model, messages, gen_kwargs)
                await llm_client._cache_set(c_key, resp, ttl=cache_ttl)
            if getattr(llm_client, "_semantic_cache", None):
                user_texts = [
                    m.get("content", "") for m in messages
                    if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)
                ]
                query_text = " ".join(user_texts).strip()
                if query_text:
                    await llm_client._semantic_cache.set(query_text, resp, model=model, ttl=cache_ttl)

        cost_val = llm_client._estimate_cost(model, getattr(resp, "prompt_tokens", 0) or 0, getattr(resp, "completion_tokens", 0) or 0) or 0.0

        resp_headers = {
            "X-Cache": "MISS" if not bypass_cache else "BYPASS",
            "X-VeloRoute-Cached": "false",
            "X-Trace-Id": trace_id,
            "X-VeloRoute-Provider": getattr(resp, "provider", "") or "unknown",
            "X-VeloRoute-Model": getattr(resp, "model", model) or model,
            "X-VeloRoute-Latency-Ms": str(getattr(resp, "latency_ms", 0.0)),
            "X-VeloRoute-Cost-USD": f"{cost_val:.6f}",
            "X-VeloRoute-Retries": str(getattr(resp, "retries", 0)),
            "X-VeloRoute-Fallback-Used": "true" if getattr(resp, "fallback_used", False) else "false",
        }
        if queued_ms > 0:
            resp_headers["X-RateLimit-Queued-Ms"] = str(queued_ms)
        if is_canary:
            resp_headers["X-VeloRoute-Canary"] = "true"
            resp_headers["X-VeloRoute-Canary-Model"] = model
        if shadow_model:
            resp_headers["X-VeloRoute-Shadow-Target"] = shadow_model
        if g_mgr and g_mgr.counter > 0:
            resp_headers["X-Guardrail-Status"] = "sanitized"
            resp_headers["X-Guardrail-PII-Masked"] = str(g_mgr.counter)
        elif guardrail_mode != "off":
            resp_headers["X-Guardrail-Status"] = "passed"
        if injection_protection:
            resp_headers["X-Guardrail-Injection-Score"] = str(inj_score)
        resp_payload = {
            "id": resp.id or f"chatcmpl-{secrets.token_hex(12)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": display_model or resp.model,
            "choices": [{"index": 0, "message": msg_dict, "finish_reason": finish_reason}],
            "usage": {
                "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens,
                "total_tokens": resp.prompt_tokens + resp.completion_tokens,
            },
        }
        return JSONResponse(content=resp_payload, headers=resp_headers)
    except Exception as exc:
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            count_estimate_when_missing=False,
        )
        return _proxy_error_response(exc)


@router.post("/v1/embeddings")
async def openai_proxy_embeddings(req: Dict[str, Any], request: Request):
    model = req.get("model")
    if not model:
        raise HTTPException(400, "Missing 'model' field")
    display_model = req.get("display_model") or model
    input_data = req.get("input")
    if input_data is None:
        raise HTTPException(400, "Missing 'input' field")

    estimated_tokens = count_tokens(input_data, model=model)
    gateway_key, reservation_id = await _authorize_gateway_request(
        request, model=model, estimated_tokens=estimated_tokens
    )
    try:
        resp = await llm_client.embed(
            model=model,
            input=input_data,
            dimensions=req.get("dimensions"),
            encoding_format=req.get("encoding_format"),
            user=req.get("user"),
        )
        prompt_tokens = getattr(resp.usage, "prompt_tokens", 0) or getattr(
            resp.usage, "total_tokens", 0
        )
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            prompt_tokens=prompt_tokens,
            estimated_tokens=estimated_tokens,
        )
        return {
            "object": "list",
            "data": [d.model_dump() for d in resp.data],
            "model": display_model or resp.model,
            "usage": resp.usage.model_dump(),
        }
    except Exception as exc:
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            count_estimate_when_missing=False,
        )
        return _proxy_error_response(exc)


@router.post("/v1/images/generations")
async def openai_proxy_image_generations(req: Dict[str, Any], request: Request):
    model = req.get("model")
    prompt = req.get("prompt")
    if not isinstance(model, str) or not model.strip():
        raise HTTPException(400, "Missing 'model' field")
    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(400, "Missing 'prompt' field")
    if "n" in req and (not isinstance(req["n"], int) or isinstance(req["n"], bool) or req["n"] < 1):
        raise HTTPException(400, "'n' must be a positive integer")

    estimated_prompt_tokens = count_tokens(prompt, model=model)
    gateway_key, reservation_id = await _authorize_gateway_request(
        request,
        model=model,
        estimated_tokens=estimated_prompt_tokens,
        # Image pricing is per-image/provider-specific; token pricing cannot
        # safely enforce a spend budget for this endpoint.
        budget_pricing_available=False,
    )
    forward_headers = extract_forward_headers(dict(request.headers))
    params = {key: value for key, value in req.items() if key not in {"model", "prompt"}}
    try:
        result = await llm_client.image_generate(
            model=model,
            prompt=prompt,
            params=params,
            headers=forward_headers,
        )
        if gateway_key is not None:
            await llm_client.virtual_keys.record_usage(
                gateway_key.id,
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=0,
                cost_usd=0.0,
                reserved_tokens=estimated_prompt_tokens,
                reservation_id=reservation_id,
            )
            llm_client.metrics.inc_counter(
                "veloroute_gateway_requests_total", {"result": "completed"}
            )
        return result
    except Exception as exc:
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            count_estimate_when_missing=False,
        )
        return _proxy_error_response(exc)


@router.post("/v1/audio/transcriptions")
async def openai_proxy_audio_transcriptions(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: str = Form("json"),
    temperature: Optional[float] = Form(None),
):
    gateway_key, reservation_id = await _authorize_gateway_request(
        request,
        model=model,
        # Transcription responses do not expose usage, so token pricing cannot
        # safely reconcile a spend budget for audio requests.
        budget_pricing_available=False,
    )
    try:
        file_bytes = await file.read()
        res = await llm_client.audio_transcribe(
            file_bytes=file_bytes,
            filename=file.filename or "audio.wav",
            model=model,
            language=language,
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
        )
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            count_estimate_when_missing=False,
        )
        return res
    except Exception as exc:
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            count_estimate_when_missing=False,
        )
        return _proxy_error_response(exc)


@router.post("/v1/audio/speech")
async def openai_proxy_audio_speech(req: Dict[str, Any], request: Request):
    model = req.get("model", "tts-1")
    input_text = req.get("input")
    if not input_text:
        raise HTTPException(400, "Missing 'input' field")
    estimated_tokens = count_tokens(input_text, model=model)
    gateway_key, reservation_id = await _authorize_gateway_request(
        request,
        model=model,
        estimated_tokens=estimated_tokens,
        # TTS usage is priced per audio output, not by the input text tokens.
        budget_pricing_available=False,
    )
    voice = req.get("voice", "alloy")
    response_format = req.get("response_format", "mp3")
    speed = float(req.get("speed", 1.0))
    try:
        audio_bytes = await llm_client.audio_speech(
            input_text=input_text,
            model=model,
            voice=voice,
            response_format=response_format,
            speed=speed,
        )
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            prompt_tokens=estimated_tokens,
            estimated_tokens=estimated_tokens,
        )
        media_type = "audio/mpeg" if response_format == "mp3" else "audio/wav"
        return Response(content=audio_bytes, media_type=media_type)
    except Exception as exc:
        await _record_gateway_usage(
            gateway_key,
            reservation_id,
            model=model,
            count_estimate_when_missing=False,
        )
        return _proxy_error_response(exc)


@router.get("/v1/models")
async def list_models_openai(request: Request):
    gateway_key, reservation_id = await _authorize_gateway_request(
        request, check_model=False
    )
    all_models = []

    for alias_name, target in llm_client.list_aliases().items():
        all_models.append({
            "id": alias_name,
            "object": "model",
            "created": 1677858200,
            "owned_by": "virtual",
            "root": target,
        })

    if hasattr(llm_client.router, "groups") and llm_client.router.groups:
        for group_name in llm_client.router.groups.list_all().keys():
            all_models.append({
                "id": group_name,
                "object": "model",
                "created": 1677858200,
                "owned_by": "group",
            })

    for provider in llm_client.get_providers():
        provider_lower = provider.lower()
        try:
            models = await llm_client.get_models(provider_lower)
        except Exception:
            models = []
        for model in models:
            all_models.append({
                "id": f"{provider_lower}/{model}",
                "object": "model",
                "created": 1677858200,
                "owned_by": provider_lower,
            })

    if gateway_key is not None:
        all_models = [
            model for model in all_models
            if _key_can_access_model(gateway_key, model["id"], model.get("root", ""))
        ]
        await _record_gateway_usage(gateway_key, reservation_id, model="models")
    return {"object": "list", "data": all_models}


@router.get("/v1/models/{model_id:path}")
async def get_model_openai(model_id: str, request: Request):
    gateway_key, reservation_id = await _authorize_gateway_request(
        request, model=model_id, check_model=True
    )
    if gateway_key is not None:
        await _record_gateway_usage(gateway_key, reservation_id, model="models")
    owned_by = model_id.split("/", 1)[0] if "/" in model_id else "veloroute"
    return {
        "id": model_id,
        "object": "model",
        "created": 1677858200,
        "owned_by": owned_by,
        "root": model_id,
    }


@router.post("/v1/completions")
async def openai_proxy_completions(req: Dict[str, Any], request: Request):
    model = req.get("model")
    if not model:
        raise HTTPException(400, "Missing 'model' field")
    display_model = req.get("display_model") or model
    raw_prompt = req.get("prompt", "")
    if isinstance(raw_prompt, list):
        prompt_text = "\n".join(str(p) for p in raw_prompt)
    else:
        prompt_text = str(raw_prompt)
    chat_req = dict(req)
    chat_req["messages"] = [{"role": "user", "content": prompt_text}]
    chat_req["display_model"] = display_model

    stream = req.get("stream", False)
    if stream:
        orig_stream_resp = await openai_proxy_chat_completions(chat_req, request)
        if not isinstance(orig_stream_resp, StreamingResponse):
            return orig_stream_resp

        async def text_event_generator():
            async for chunk in orig_stream_resp.body_iterator:
                chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                if chunk_str.startswith("data: ") and not chunk_str.startswith("data: [DONE]"):
                    try:
                        payload = json.loads(chunk_str[6:])
                        choices = payload.get("choices", [])
                        if choices:
                            delta_content = choices[0].get("delta", {}).get("content", "")
                            text_choice = {
                                "text": delta_content,
                                "index": 0,
                                "logprobs": None,
                                "finish_reason": choices[0].get("finish_reason"),
                            }
                            text_payload = {
                                "id": payload.get("id"),
                                "object": "text_completion",
                                "created": payload.get("created"),
                                "model": payload.get("model", display_model),
                                "choices": [text_choice],
                            }
                            if "usage" in payload:
                                text_payload["usage"] = payload["usage"]
                            yield f"data: {json.dumps(text_payload)}\n\n"
                            continue
                    except Exception:
                        pass
                yield chunk_str

        return StreamingResponse(
            text_event_generator(),
            media_type="text/event-stream",
            headers=dict(orig_stream_resp.headers),
        )

    res = await openai_proxy_chat_completions(chat_req, request)
    if isinstance(res, JSONResponse):
        try:
            body = json.loads(res.body.decode("utf-8"))
            if "choices" in body and isinstance(body["choices"], list) and len(body["choices"]) > 0:
                choice0 = body["choices"][0]
                text_content = choice0.get("message", {}).get("content", "")
                text_payload = {
                    "id": body.get("id", f"cmpl-{secrets.token_hex(12)}"),
                    "object": "text_completion",
                    "created": body.get("created", int(time.time())),
                    "model": body.get("model", display_model),
                    "choices": [
                        {
                            "text": text_content,
                            "index": 0,
                            "logprobs": None,
                            "finish_reason": choice0.get("finish_reason", "stop"),
                        }
                    ],
                    "usage": body.get("usage", {}),
                }
                return JSONResponse(content=text_payload, status_code=res.status_code, headers=dict(res.headers))
        except Exception:
            pass
        return res
    if isinstance(res, dict) and "choices" in res:
        choice0 = res["choices"][0]
        text_content = choice0.get("message", {}).get("content", "")
        return {
            "id": res.get("id", f"cmpl-{secrets.token_hex(12)}"),
            "object": "text_completion",
            "created": res.get("created", int(time.time())),
            "model": res.get("model", display_model),
            "choices": [
                {
                    "text": text_content,
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": choice0.get("finish_reason", "stop"),
                }
            ],
            "usage": res.get("usage", {}),
        }
    return res


# ─── Provider-Specific Dedicated Endpoints (/p/<provider>/v1/...) ─────────────

def _normalize_provider_model(provider: str, req_model: str) -> str:
    p_lower = provider.lower()
    if not req_model:
        raise HTTPException(400, "Missing 'model' field")
    m_str = req_model.strip()
    if "/" in m_str:
        prefix, rest = m_str.split("/", 1)
        if prefix.lower() == p_lower:
            return m_str
        # If the user included another known provider prefix while using this dedicated provider URL,
        # strip that mismatched provider prefix so it routes to this dedicated provider.
        if prefix.lower() in llm_client.get_providers():
            return f"{p_lower}/{rest}"
        return f"{p_lower}/{m_str}"
    return f"{p_lower}/{m_str}"


@router.get("/p/{provider}")
@router.get("/p/{provider}/")
@router.get("/p/{provider}/v1")
@router.get("/p/{provider}/v1/")
async def provider_root_probe(provider: str):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")
    return {
        "status": "ok",
        "provider": p_lower,
        "base_url": f"/p/{p_lower}/v1",
        "models_url": f"/p/{p_lower}/v1/models",
    }


@router.get("/p/{provider}/v1/models")
@router.get("/p/{provider}/models")
async def provider_list_models(provider: str, request: Request):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")

    gateway_key, reservation_id = await _authorize_gateway_request(
        request, check_model=False
    )

    try:
        models = await llm_client.get_models(p_lower)
    except Exception:
        models = []

    data = []
    for raw_id in models:
        model_id = raw_id[len(p_lower) + 1:] if raw_id.lower().startswith(f"{p_lower}/") else raw_id
        if gateway_key is not None:
            if not (_key_can_access_model(gateway_key, model_id, "") or
                    _key_can_access_model(gateway_key, f"{p_lower}/{model_id}", "")):
                continue
        data.append({
            "id": model_id,
            "object": "model",
            "created": 1677858200,
            "owned_by": p_lower,
            "root": model_id,
        })

    if gateway_key is not None:
        await _record_gateway_usage(gateway_key, reservation_id, model="models")
    return {"object": "list", "data": data}


@router.get("/p/{provider}/v1/models/{model_id:path}")
@router.get("/p/{provider}/models/{model_id:path}")
async def provider_get_model(provider: str, model_id: str, request: Request):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")
    target_model = _normalize_provider_model(p_lower, model_id)
    gateway_key, reservation_id = await _authorize_gateway_request(
        request, model=target_model, check_model=True
    )
    if gateway_key is not None:
        await _record_gateway_usage(gateway_key, reservation_id, model="models")
    return {
        "id": model_id,
        "object": "model",
        "created": 1677858200,
        "owned_by": p_lower,
        "root": model_id,
    }


@router.post("/p/{provider}/v1/chat/completions")
@router.post("/p/{provider}/chat/completions")
async def provider_proxy_chat_completions(provider: str, req: Dict[str, Any], request: Request):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")

    orig_model = req.get("model", "")
    target_model = _normalize_provider_model(p_lower, orig_model)
    routed_req = dict(req)
    routed_req["model"] = target_model
    routed_req["display_model"] = orig_model
    res = await openai_proxy_chat_completions(routed_req, request)
    if isinstance(res, JSONResponse):
        try:
            body = json.loads(res.body.decode("utf-8"))
            if "model" in body and orig_model:
                body["model"] = orig_model
                return JSONResponse(content=body, status_code=res.status_code, headers=dict(res.headers))
        except Exception:
            pass
        return res
    elif isinstance(res, dict) and "model" in res and orig_model:
        res["model"] = orig_model
    return res


@router.post("/p/{provider}/v1/completions")
@router.post("/p/{provider}/completions")
async def provider_proxy_completions(provider: str, req: Dict[str, Any], request: Request):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")
    orig_model = req.get("model", "")
    target_model = _normalize_provider_model(p_lower, orig_model)
    routed_req = dict(req)
    routed_req["model"] = target_model
    routed_req["display_model"] = orig_model
    res = await openai_proxy_completions(routed_req, request)
    if isinstance(res, JSONResponse):
        try:
            body = json.loads(res.body.decode("utf-8"))
            if "model" in body and orig_model:
                body["model"] = orig_model
                return JSONResponse(content=body, status_code=res.status_code, headers=dict(res.headers))
        except Exception:
            pass
        return res
    if isinstance(res, dict) and "model" in res and orig_model:
        res["model"] = orig_model
    return res


@router.post("/p/{provider}/v1/embeddings")
@router.post("/p/{provider}/embeddings")
async def provider_proxy_embeddings(provider: str, req: Dict[str, Any], request: Request):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")
    orig_model = req.get("model", "")
    target_model = _normalize_provider_model(p_lower, orig_model)
    routed_req = dict(req)
    routed_req["model"] = target_model
    routed_req["display_model"] = orig_model
    res = await openai_proxy_embeddings(routed_req, request)
    if isinstance(res, dict) and "model" in res and orig_model:
        res["model"] = orig_model
    return res


@router.post("/p/{provider}/v1/images/generations")
@router.post("/p/{provider}/images/generations")
async def provider_proxy_images(provider: str, req: Dict[str, Any], request: Request):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")
    orig_model = req.get("model", "")
    target_model = _normalize_provider_model(p_lower, orig_model)
    routed_req = dict(req)
    routed_req["model"] = target_model
    routed_req["display_model"] = orig_model
    return await openai_proxy_image_generations(routed_req, request)


@router.post("/p/{provider}/v1/audio/transcriptions")
@router.post("/p/{provider}/audio/transcriptions")
async def provider_proxy_audio_transcriptions(
    provider: str,
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: str = Form("json"),
    temperature: Optional[float] = Form(None),
):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")
    target_model = _normalize_provider_model(p_lower, model)
    return await openai_proxy_audio_transcriptions(
        request=request,
        file=file,
        model=target_model,
        language=language,
        prompt=prompt,
        response_format=response_format,
        temperature=temperature,
    )


@router.post("/p/{provider}/v1/audio/speech")
@router.post("/p/{provider}/audio/speech")
async def provider_proxy_audio_speech(provider: str, req: Dict[str, Any], request: Request):
    p_lower = provider.lower()
    if p_lower not in llm_client.get_providers():
        raise HTTPException(404, f"Provider '{provider}' not found or not configured")
    orig_model = req.get("model", "tts-1")
    target_model = _normalize_provider_model(p_lower, orig_model)
    routed_req = dict(req)
    routed_req["model"] = target_model
    routed_req["display_model"] = orig_model
    return await openai_proxy_audio_speech(routed_req, request)


@router.get("/p/{provider}/api/v1/models")
async def provider_api_list_models(provider: str, request: Request):
    return await provider_list_models(provider, request)

@router.get("/p/{provider}/version")
@router.get("/p/{provider}/v1/version")
@router.get("/version")
async def provider_version_probe(provider: Optional[str] = None):
    return {"version": "2.0.0", "status": "ok", "provider": provider or "veloroute"}

@router.get("/p/{provider}/props")
@router.get("/p/{provider}/v1/props")
@router.get("/props")
async def provider_props_probe(provider: Optional[str] = None):
    return {"status": "ok", "provider": provider or "veloroute"}

@router.get("/p/{provider}/lmstudio-greeting")
@router.get("/lmstudio-greeting")
async def provider_lmstudio_probe(provider: Optional[str] = None):
    return {"status": "ok", "message": "VeloRoute Gateway Ready"}

@router.get("/p/{provider}/health/readiness/details")
@router.get("/health/readiness/details")
async def provider_health_readiness(provider: Optional[str] = None):
    return {"status": "ready"}

@router.get("/p/{provider}/v1/model/info")
@router.get("/p/{provider}/v1/sub2api/billing")
async def provider_sub2api_billing(provider: Optional[str] = None):
    return {"status": "ok", "balance": 999.0, "currency": "USD"}

@router.get("/p/{provider}/api/v1/settings/public")
async def provider_settings_public(provider: Optional[str] = None):
    return {}
