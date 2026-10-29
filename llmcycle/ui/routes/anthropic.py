"""
Anthropic Messages API Protocol Adapter
=======================================
Implements /v1/messages conforming to the Anthropic Messages API specification.
Translates Anthropic requests into LLMCycle completions and streams Anthropic SSE events.
Inspired by LiteLLM, One-API, Relay, and Simple One API.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .deps import llm_client
from llmcycle.schema import Message
from llmcycle.gateway.keys import GatewayAuthError

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
            )
        except GatewayAuthError as gae:
            raise HTTPException(
                status_code=gae.status_code,
                detail={"type": "error", "error": {"type": gae.code, "message": gae.message}},
            )

    # 2. Convert Anthropic messages to LLMCycle messages
    cycle_messages: List[Message] = []
    if req.system:
        system_text = _format_content_to_text(req.system)
        cycle_messages.append(Message(role="system", content=system_text))

    for m in req.messages:
        text = _format_content_to_text(m.content)
        cycle_messages.append(Message(role=m.role, content=text))

    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

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
                    "model": req.model,
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
                    req.model,
                    messages=cycle_messages,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                )
                async for chunk in stream_iter:
                    delta_text = chunk.content or ""
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
                    total_tokens = input_tokens + max(1, out_tokens)
                    await llm_client.virtual_keys.record_usage(
                        authorized_key.id,
                        tokens=total_tokens,
                        model=req.model,
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
            req.model,
            messages=cycle_messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"type": "error", "error": {"type": "api_error", "message": str(exc)}},
        ) from exc

    in_tokens = getattr(resp, "prompt_tokens", 0) or 0
    out_tokens = getattr(resp, "completion_tokens", 0) or 0

    if authorized_key and reservation_id:
        await llm_client.virtual_keys.record_usage(
            authorized_key.id,
            tokens=in_tokens + out_tokens,
            model=req.model,
            cost_usd=resp.cost_usd or 0.0,
            reservation_id=reservation_id,
        )

    anthropic_resp = {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": req.model,
        "content": [
            {
                "type": "text",
                "text": resp.content or "",
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
