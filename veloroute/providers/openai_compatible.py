"""
OpenAI-Compatible Provider
===========================
Handles all REST-based providers using the OpenAI chat/completions API spec.
Implements full error classification (400/401/402/403/404/429/500/502/503/504)
mapped to unified VeloRoute exception types so the router knows exactly how to react.
"""
from __future__ import annotations
import asyncio
import json
import time
import logging
import threading
import weakref
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List, Union, Dict, Any, Tuple

import httpx

from veloroute.schema import (
    CompletionRequest, CompletionResponse,
    EmbeddingRequest, EmbeddingResponse, EmbeddingData, EmbeddingUsage,
)
from veloroute.providers.base import LLMProvider
from veloroute.providers.cache import get_model_info_cache
from veloroute.core.errors import classify_http_error, ContentPolicyError, AuthenticationError, VeloRouteError
from veloroute.core.stream import SSEParser
from veloroute.utils import merge_request_headers

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)


class OpenAICompatibleProvider(LLMProvider):
    """
    Universal OpenAI-compatible HTTP provider.
    Works with: OpenAI, DeepSeek, Groq, Mistral, Together, Fireworks,
    Perplexity, OpenRouter, Anthropic (via compat layer), and 40+ more.
    """

    def __init__(self, base_url: str, provider_name: str = "unknown", proxy: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_name
        self.proxy = proxy
        # Shared LRU + disk cache (singleton across all provider instances)
        self._cache = get_model_info_cache()
        # One pooled AsyncClient per event loop.  Creating a new client for
        # every request (the old behaviour) disabled keep-alive/TLS session
        # reuse and leaked connection pools under load.  Keying by loop keeps
        # the provider safe to use from multiple event loops (tests, threads).
        self._clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = (
            weakref.WeakKeyDictionary()
        )
        self._client_lock = threading.Lock()

    def _get_client(self, timeout: Optional[httpx.Timeout] = None) -> httpx.AsyncClient:
        """Return the pooled client bound to the current event loop."""
        loop = asyncio.get_running_loop()
        with self._client_lock:
            client = self._clients.get(loop)
            if client is None or client.is_closed:
                client = httpx.AsyncClient(
                    timeout=timeout or TIMEOUT,
                    proxy=self.proxy,
                )
                self._clients[loop] = client
            return client

    @asynccontextmanager
    async def _client(self, timeout: Optional[httpx.Timeout] = None):
        """Async context manager that yields the pooled client (no close)."""
        yield self._get_client(timeout)

    async def aclose(self) -> None:
        """Close the pooled client for the current event loop."""
        loop = asyncio.get_running_loop()
        with self._client_lock:
            client = self._clients.pop(loop, None)
        if client is not None:
            await client.aclose()

    async def aclose_all(self) -> None:
        """Best-effort close of every pooled client (shutdown only)."""
        with self._client_lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            try:
                await client.aclose()
            except Exception:
                pass

    def _headers(self, api_key: str, extra_headers: Optional[Dict[str, str]] = None) -> dict:
        base = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        return merge_request_headers(base, extra_headers)

    async def get_models_detailed(self, api_key: str, raise_on_error: bool = False) -> list[dict]:
        """Return raw model objects from upstream /models endpoint."""
        if self.base_url.startswith("mock://") or self.provider_name.lower() == "mock":
            return [
                {"id": "mock/gpt-4o", "name": "Mock GPT-4o", "context_window": 128000},
                {"id": "mock/claude-3-7-sonnet", "name": "Mock Claude 3.7", "context_window": 200000},
                {"id": "mock/deepseek-r1", "name": "Mock DeepSeek R1", "context_window": 64000},
            ]
        client = self._get_client()
        try:
            resp = await client.get(
                f"{self.base_url}/models",
                headers=self._headers(api_key),
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    items = data.get("data") or data.get("models") or []
                    if isinstance(items, list):
                        result = []
                        for item in items:
                            if isinstance(item, dict) and "id" in item:
                                result.append(item)
                            elif isinstance(item, str):
                                result.append({"id": item})
                        return result
                elif isinstance(data, list):
                    return [{"id": m} if isinstance(m, str) else m for m in data if isinstance(m, (dict, str))]
            elif raise_on_error:
                if resp.status_code in (401, 403):
                    raise AuthenticationError(f"HTTP {resp.status_code}: Authentication failed on upstream {self.base_url}/models")
                elif resp.status_code == 404:
                    raise VeloRouteError(f"HTTP 404: /models endpoint not found at {self.base_url}/models")
                else:
                    raise VeloRouteError(f"HTTP {resp.status_code}: Upstream /models returned status {resp.status_code}")
            logger.warning(f"[{self.provider_name}] /models returned {resp.status_code}")
            return []
        except (AuthenticationError, VeloRouteError):
            raise
        except Exception as e:
            logger.debug(f"[{self.provider_name}] get_models_detailed failed: {e}")
            if raise_on_error:
                raise VeloRouteError(f"Could not connect to {self.base_url}/models: {e}")
            return []

    async def get_models(self, api_key: str) -> list[str]:
        """Return sorted list of available model IDs from the provider."""
        items = await self.get_models_detailed(api_key)
        return sorted({m["id"] for m in items if isinstance(m, dict) and m.get("id")})

    async def get_model_info(self, model_id: str, api_key: str) -> dict:
        """
        Fetch live metadata for a single model — called at most ONCE per model
        across the entire process lifetime (and across restarts via disk cache).
        """
        cache_key = f"{self.provider_name}/{model_id}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        info: dict = {}
        client = self._get_client()
        timeout = httpx.Timeout(10.0)

        try:
            resp = await client.get(
                f"{self.base_url}/models/{model_id}",
                headers=self._headers(api_key),
                timeout=timeout,
            )
            if resp.status_code == 200:
                info = resp.json()
        except Exception as e:
            logger.debug(
                f"[{self.provider_name}] GET /models/{model_id} failed: {e}"
            )

        if not info:
            try:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(api_key),
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    raw = resp.json()
                    items = raw.get("data") or raw.get("models") or []
                    for m in items:
                        if isinstance(m, dict) and m.get("id") == model_id:
                            info = m
                            break
            except Exception as e:
                logger.debug(
                    f"[{self.provider_name}] GET /models list scan failed: {e}"
                )

        for alias in ("context_length", "max_context_length", "max_tokens", "n_ctx"):
            if alias in info and "context_window" not in info:
                info["context_window"] = info[alias]
                break

        raw_pricing = info.get("pricing", {})
        if raw_pricing and "input" not in raw_pricing:
            p_in  = (raw_pricing.get("prompt")     or raw_pricing.get("input")
                     or raw_pricing.get("input_cost_per_token"))
            p_out = (raw_pricing.get("completion") or raw_pricing.get("output")
                     or raw_pricing.get("output_cost_per_token"))
            if p_in is not None and p_out is not None:
                try:
                    info["pricing"] = {
                        "input":  float(p_in)  * 1000,
                        "output": float(p_out) * 1000,
                    }
                except (TypeError, ValueError):
                    pass

        self._cache.set(cache_key, info)
        logger.debug(
            f"[{self.provider_name}] model info cached for '{model_id}': "
            f"ctx={info.get('context_window')} pricing={info.get('pricing')}"
        )
        return info

    async def generate(
        self,
        request: CompletionRequest,
        api_key: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> CompletionResponse:
        if self.base_url.startswith("mock://") or self.provider_name.lower() == "mock":
            import secrets
            prompt_tokens = max(1, len(str(request.messages)) // 4)
            completion_tokens = 20
            return CompletionResponse(
                id=f"chatcmpl-mock-{secrets.token_hex(6)}",
                model=request.model,
                provider=self.provider_name,
                content=f"Simulated mock completion response for model '{request.model}'.",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=1.5,
                finish_reason="stop",
            )
        payload = request.to_api_dict()
        payload["stream"] = False

        t0 = time.monotonic()
        client = self._get_client()
        try:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(api_key, extra_headers=headers),
                json=payload,
                timeout=TIMEOUT,
            )
        except httpx.ConnectError as e:
            raise classify_http_error(503, str(e), self.provider_name, request.model)
        except httpx.TimeoutException as e:
            raise classify_http_error(504, str(e), self.provider_name, request.model)

        latency_ms = (time.monotonic() - t0) * 1000

        if resp.status_code != 200:
            raise classify_http_error(resp.status_code, resp.text, self.provider_name, request.model)

        try:
            data = resp.json()
        except Exception as e:
            raise classify_http_error(resp.status_code, resp.text, self.provider_name, request.model)

        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices or not isinstance(choices, list):
            raise classify_http_error(resp.status_code, resp.text, self.provider_name, request.model)

        choice = choices[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        usage = data.get("usage", {}) if isinstance(data, dict) else {}

        raw_tool_calls = message.get("tool_calls") or []
        tool_calls = raw_tool_calls if raw_tool_calls else None
        content = message.get("content") or ""
        reasoning_content = message.get("reasoning_content") or message.get("reasoning") or None

        return CompletionResponse(
            id=data.get("id", ""),
            model=data.get("model", request.model),
            provider=self.provider_name,
            content=content,
            reasoning_content=reasoning_content,
            prompt_tokens=usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0,
            completion_tokens=usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
        )

    def _convert_sse_event(
        self,
        event: Dict[str, Any],
        stream_id: str,
        stream_model: str,
    ) -> List[Dict[str, Any]]:
        """Translate one OpenAI SSE chunk into zero or more structured events."""
        out: List[Dict[str, Any]] = []
        if not isinstance(event, dict):
            return out

        if event.get("error"):
            err = event["error"]
            raise classify_http_error(
                502,
                json.dumps(err) if not isinstance(err, str) else err,
                self.provider_name,
                stream_model,
            )

        stream_id = event.get("id") or stream_id
        stream_model = event.get("model") or stream_model

        usage = event.get("usage")
        if isinstance(usage, dict):
            out.append({
                "type": "usage",
                "usage": usage,
                "id": stream_id,
                "model": stream_model,
            })

        choices = event.get("choices")
        if not choices or not isinstance(choices, list):
            return out

        choice = choices[0]
        if not isinstance(choice, dict):
            return out

        if choice.get("finish_reason"):
            out.append({
                "type": "finish",
                "finish_reason": choice["finish_reason"],
                "id": stream_id,
                "model": stream_model,
            })

        delta = choice.get("delta")
        if not isinstance(delta, dict):
            return out

        text = delta.get("content")
        if isinstance(text, str) and text:
            out.append({
                "type": "content",
                "text": text,
                "id": stream_id,
                "model": stream_model,
            })

        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            out.append({
                "type": "reasoning",
                "text": reasoning,
                "id": stream_id,
                "model": stream_model,
            })

        raw_tools = delta.get("tool_calls")
        if isinstance(raw_tools, list):
            for tc in raw_tools:
                if not isinstance(tc, dict):
                    continue
                tool_call: Dict[str, Any] = {"index": tc.get("index", 0)}
                for key in ("id", "type"):
                    if tc.get(key):
                        tool_call[key] = tc[key]
                fn = tc.get("function")
                if isinstance(fn, dict):
                    fn_out: Dict[str, Any] = {}
                    if fn.get("name"):
                        fn_out["name"] = fn["name"]
                    if fn.get("arguments") is not None:
                        fn_out["arguments"] = fn["arguments"]
                    if fn_out:
                        tool_call["function"] = fn_out
                out.append({
                    "type": "tool_call",
                    "tool_call": tool_call,
                    "id": stream_id,
                    "model": stream_model,
                })

        return out

    async def generate_stream_events(
        self,
        request: CompletionRequest,
        api_key: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream structured events (content / reasoning / tool-call deltas /
        usage / finish / done).  ``generate_stream`` is a text-only wrapper.
        """
        if self.base_url.startswith("mock://") or self.provider_name.lower() == "mock":
            import secrets
            s_id = f"chatcmpl-mock-{secrets.token_hex(6)}"
            chunks = ["Simulated", " mock", " streaming", " chunk", " from", " VeloRoute."]
            for tok in chunks:
                yield {
                    "type": "content",
                    "text": tok,
                    "id": s_id,
                    "model": request.model,
                }
            yield {
                "type": "finish",
                "finish_reason": "stop",
                "id": s_id,
                "model": request.model,
            }
            yield {"type": "done"}
            return
        payload = request.to_api_dict()
        payload["stream"] = True

        client = self._get_client()
        stream_id = ""
        stream_model = request.model
        saw_done = False

        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(api_key, extra_headers=headers),
                json=payload,
                timeout=TIMEOUT,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise classify_http_error(
                        resp.status_code,
                        body.decode(errors="replace"),
                        self.provider_name,
                        request.model,
                    )

                parser = SSEParser()
                async for chunk_bytes in resp.aiter_bytes():
                    for event in parser.feed(chunk_bytes):
                        if event.get("done"):
                            saw_done = True
                            break
                        for out in self._convert_sse_event(event, stream_id, stream_model):
                            stream_id = out.get("id") or stream_id
                            stream_model = out.get("model") or stream_model
                            yield out
                    if saw_done:
                        break

                if not saw_done:
                    for event in parser.close():
                        if event.get("done"):
                            saw_done = True
                            break
                        for out in self._convert_sse_event(event, stream_id, stream_model):
                            stream_id = out.get("id") or stream_id
                            stream_model = out.get("model") or stream_model
                            yield out

        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            raise classify_http_error(503, str(e), self.provider_name, request.model)
        except httpx.TimeoutException as e:
            raise classify_http_error(504, str(e), self.provider_name, request.model)

        yield {
            "type": "done",
            "id": stream_id,
            "model": stream_model,
        }

    async def generate_stream(
        self,
        request: CompletionRequest,
        api_key: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Backwards-compatible text-only stream."""
        async for event in self.generate_stream_events(request, api_key, headers=headers):
            if event.get("type") == "content":
                text = event.get("text")
                if text:
                    yield text

    async def ping(
        self,
        api_key: str,
        model: Optional[str] = None,
        timeout: float = 10.0,
    ) -> dict:
        """
        Probe provider with a real minimal payload to verify health and measure exact roundtrip latency.
        Attempts a 1-token probe to /chat/completions; if model is omitted or not found, falls back to /models.
        """
        if self.base_url.startswith("mock://") or self.provider_name.lower() == "mock":
            return {"status": "ok", "latency_ms": 1.0, "endpoint": "mock://internal", "probe": "mock_simulated"}
        t0 = time.monotonic()
        client_timeout = httpx.Timeout(timeout)
        client = self._get_client(client_timeout)
        probe_model = model
        if not probe_model:
            try:
                models = await self.get_models(api_key)
                if models:
                    # Prefer known chat model indicators
                    chat_candidates = [
                        m for m in models
                        if any(w in m.lower() for w in ("gpt", "chat", "claude", "gemini", "llama", "deepseek", "mistral", "qwen", "command", "sonar", "instruct"))
                        and not any(bad in m.lower() for bad in ("embed", "whisper", "tts", "dall-e", "image", "rerank", "moderation", "babbage", "davinci"))
                    ]
                    probe_model = chat_candidates[0] if chat_candidates else models[0]
            except Exception:
                pass

        if probe_model:
            try:
                payload = {
                    "model": probe_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "stream": False,
                }
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(api_key),
                    json=payload,
                    timeout=client_timeout,
                )
                latency_ms = round((time.monotonic() - t0) * 1000, 2)
                if resp.status_code == 200:
                    return {
                        "healthy": True,
                        "latency_ms": latency_ms,
                        "provider": self.provider_name,
                        "model": probe_model,
                        "status_code": 200,
                        "probe": "chat/completions",
                    }
                if resp.status_code not in (400, 404) or model:
                    err = classify_http_error(resp.status_code, resp.text, self.provider_name, probe_model)
                    return {
                        "healthy": False,
                        "latency_ms": latency_ms,
                        "provider": self.provider_name,
                        "model": probe_model,
                        "status_code": resp.status_code,
                        "error": str(err),
                        "error_type": type(err).__name__,
                        "probe": "chat/completions",
                    }
            except Exception as exc:
                if model:
                    latency_ms = round((time.monotonic() - t0) * 1000, 2)
                    return {
                        "healthy": False,
                        "latency_ms": latency_ms,
                        "provider": self.provider_name,
                        "model": probe_model,
                        "status_code": 0,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "probe": "chat/completions",
                    }

        # Fall back to GET /models when model discovery found no chat model or
        # the auto-detected model does not support the chat endpoint.
        try:
            resp = await client.get(
                f"{self.base_url}/models",
                headers=self._headers(api_key),
                timeout=client_timeout,
            )
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            if resp.status_code == 200:
                return {
                    "healthy": True,
                    "latency_ms": latency_ms,
                    "provider": self.provider_name,
                    "model": None,
                    "status_code": 200,
                    "probe": "models",
                }
            err = classify_http_error(resp.status_code, resp.text, self.provider_name, "")
            return {
                "healthy": False,
                "latency_ms": latency_ms,
                "provider": self.provider_name,
                "model": None,
                "status_code": resp.status_code,
                "error": str(err),
                "error_type": type(err).__name__,
                "probe": "models",
            }
        except Exception as exc:
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {
                "healthy": False,
                "latency_ms": latency_ms,
                "provider": self.provider_name,
                "model": None,
                "status_code": 0,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "probe": "models",
            }

    async def embeddings(
        self,
        request: EmbeddingRequest,
        api_key: str,
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> EmbeddingResponse:
        payload = request.to_api_dict()
        t0 = time.monotonic()
        client_timeout = httpx.Timeout(timeout) if timeout else TIMEOUT
        async with self._client(client_timeout) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=self._headers(api_key, extra_headers=headers),
                    json=payload,
                )
            except httpx.ConnectError as e:
                raise classify_http_error(503, str(e), self.provider_name, request.model)
            except httpx.TimeoutException as e:
                raise classify_http_error(504, str(e), self.provider_name, request.model)

            latency_ms = (time.monotonic() - t0) * 1000
            if resp.status_code != 200:
                raise classify_http_error(resp.status_code, resp.text, self.provider_name, request.model)

            data = resp.json()
            emb_data = []
            for item in data.get("data", []):
                emb_data.append(
                    EmbeddingData(
                        object=item.get("object", "embedding"),
                        index=item.get("index", 0),
                        embedding=item.get("embedding", []),
                    )
                )
            raw_usage = data.get("usage", {})
            usage = EmbeddingUsage(
                prompt_tokens=raw_usage.get("prompt_tokens", 0),
                total_tokens=raw_usage.get("total_tokens", raw_usage.get("prompt_tokens", 0)),
            )
            return EmbeddingResponse(
                object=data.get("object", "list"),
                data=emb_data,
                model=data.get("model", request.model),
                usage=usage,
                provider=self.provider_name,
                latency_ms=latency_ms,
            )

    async def audio_transcriptions(
        self,
        file_bytes: bytes,
        filename: str,
        model: str,
        api_key: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: str = "json",
        temperature: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> dict:
        files = {"file": (filename, file_bytes)}
        data: dict = {"model": model, "response_format": response_format}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        if temperature is not None:
            data["temperature"] = str(temperature)

        base_headers = {"Authorization": f"Bearer {api_key}"}
        req_headers = merge_request_headers(base_headers, headers)
        async with self._client(TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers=req_headers,
                    files=files,
                    data=data,
                )
            except httpx.ConnectError as e:
                raise classify_http_error(503, str(e), self.provider_name, model)
            except httpx.TimeoutException as e:
                raise classify_http_error(504, str(e), self.provider_name, model)

            if resp.status_code != 200:
                raise classify_http_error(resp.status_code, resp.text, self.provider_name, model)

            if response_format in ("json", "verbose_json"):
                return resp.json()
            return {"text": resp.text}

    async def audio_speech(
        self,
        input_text: str,
        model: str,
        voice: str,
        api_key: str,
        response_format: str = "mp3",
        speed: float = 1.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        payload = {
            "model": model,
            "input": input_text,
            "voice": voice,
            "response_format": response_format,
            "speed": speed,
        }
        async with self._client(TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/audio/speech",
                    headers=self._headers(api_key, extra_headers=headers),
                    json=payload,
                )
            except httpx.ConnectError as e:
                raise classify_http_error(503, str(e), self.provider_name, model)
            except httpx.TimeoutException as e:
                raise classify_http_error(504, str(e), self.provider_name, model)

            if resp.status_code != 200:
                raise classify_http_error(resp.status_code, resp.text, self.provider_name, model)

            return resp.content

    async def image_generations(
        self,
        payload: Dict[str, Any],
        api_key: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> dict:
        """Call an OpenAI-compatible image generation endpoint."""
        model = str(payload.get("model") or "")
        async with self._client(TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/images/generations",
                    headers=self._headers(api_key, extra_headers=headers),
                    json=payload,
                )
            except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                raise classify_http_error(503, str(exc), self.provider_name, model)
            except httpx.TimeoutException as exc:
                raise classify_http_error(504, str(exc), self.provider_name, model)

            if resp.status_code != 200:
                raise classify_http_error(
                    resp.status_code, resp.text, self.provider_name, model
                )
            return resp.json()
