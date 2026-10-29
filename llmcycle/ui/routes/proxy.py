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
from llmcycle.core.errors import APIConnectionError, AllProvidersFailedError
from llmcycle.gateway.keys import GatewayAuthError, VirtualKey
from llmcycle.utils import count_message_tokens, count_tokens, extract_forward_headers

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
        )
    except GatewayAuthError:
        llm_client.metrics.inc_counter(
            "llmcycle_gateway_requests_total", {"result": "denied"}
        )
        raise
    llm_client.metrics.inc_counter(
        "llmcycle_gateway_requests_total", {"result": "authorized"}
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
        "llmcycle_gateway_requests_total", {"result": "completed"}
    )


def _safe_message_token_estimate(messages: Any, model: str) -> int:
    try:
        return max(0, count_message_tokens(messages or [], model=model))
    except (TypeError, ValueError, AttributeError):
        return 0


def _key_can_access_model(record: VirtualKey, model_id: str, root: str = "") -> bool:
    return not record.allowed_models or any(
        fnmatch.fnmatchcase(candidate, pattern)
        for candidate in (model_id, root)
        if candidate
        for pattern in record.allowed_models
    )


@router.post("/v1/chat/completions")
async def openai_proxy_chat_completions(req: Dict[str, Any], request: Request):
    model = req.get("model")
    if not model:
        raise HTTPException(400, "Missing 'model' field")

    messages = req.get("messages", [])
    prompt_tokens_est = _safe_message_token_estimate(messages, model)
    gateway_key, reservation_id = await _authorize_gateway_request(
        request, model=model, estimated_tokens=prompt_tokens_est
    )
    stream = req.get("stream", False)
    forward_headers = extract_forward_headers(dict(request.headers))

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

    if stream:
        async def event_generator():
            completion_tokens_est = 0
            producer_task = None
            chunk_id = f"chatcmpl-{secrets.token_hex(12)}"
            created_ts = int(time.time())
            include_usage = req.get("stream_options", {}).get("include_usage", False)
            queue: asyncio.Queue = asyncio.Queue()

            async def stream_producer():
                try:
                    async for text in llm_client.stream(
                        model=model,
                        messages=messages,
                        headers=forward_headers,
                        **gen_kwargs,
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
                        completion_tokens_est += max(1, len(val) // 4)
                        chunk = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
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
                            "model": model,
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
                        break
                    else:
                        raise val

                await producer_task
            except asyncio.CancelledError:
                raise
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
                await _record_gateway_usage(
                    gateway_key,
                    reservation_id,
                    model=model,
                    prompt_tokens=prompt_tokens_est,
                    completion_tokens=completion_tokens_est,
                    estimated_tokens=prompt_tokens_est,
                )

        headers = {
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)

    try:
        resp = await llm_client.complete(
            model=model, messages=messages, headers=forward_headers, **gen_kwargs
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
        if getattr(resp, "reasoning_content", None):
            msg_dict["reasoning_content"] = resp.reasoning_content
        if getattr(resp, "tool_calls", None):
            msg_dict["tool_calls"] = resp.tool_calls
        finish_reason = "tool_calls" if getattr(resp, "tool_calls", None) else "stop"
        return {
            "id": resp.id or f"chatcmpl-{secrets.token_hex(12)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": resp.model,
            "choices": [{"index": 0, "message": msg_dict, "finish_reason": finish_reason}],
            "usage": {
                "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens,
                "total_tokens": resp.prompt_tokens + resp.completion_tokens,
            },
        }
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
            "model": resp.model,
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
                "llmcycle_gateway_requests_total", {"result": "completed"}
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
