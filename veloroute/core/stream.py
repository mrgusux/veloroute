"""
StreamResilienceManager - Smart LLM Manager
============================================
Smart retry logic:
  1. User sets max_retries (default 2) and retry_delay (default 1.0s)
  2. Before each retry, check if more keys exist for the same provider
     - Yes → rotate key and retry immediately (no delay)
     - No  → wait retry_delay, then fall over to next provider
  3. Across all providers: respect sort order from router

Scenarios handled:
  SCENARIO 1 – Provider drops connection mid-stream
    → Capture partial text, inject context, failover

  SCENARIO 2 – Rate-limit / Auth error during stream
    → Rotate key if available, else failover with retry_delay wait

  SCENARIO 3 – Consumer stops (GeneratorExit / stop_event / CancelledError)
    → Clean exit, HTTP connection released

  SCENARIO 4 – Content policy
    → Fail immediately, no retry ever

Smart retry decision tree:
  On ANY retriable error:
    if provider has another usable key:
       → rotate key, retry NOW (counts toward max_retries)
    elif retries_remaining > 0:
       → wait retry_delay seconds, try next provider
    else:
       → move to next provider in fallback chain immediately
"""
from __future__ import annotations
import asyncio
import json
import logging
import random
import secrets
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Sequence, Tuple, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from veloroute.core.router import RoutingStrategy

from veloroute.schema import CompletionRequest, CompletionResponse, Message
from veloroute.core.errors import (
    VeloRouteError, RateLimitError, AuthenticationError,
    QuotaExceededError, ContentPolicyError,
    PermissionDeniedError, NotFoundError, BadRequestError,
    InternalServerError, BadGatewayError, ServiceUnavailableError,
    GatewayTimeoutError, APIConnectionError, APIResponseError,
    AllProvidersFailedError,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY = 1.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_MAX_DELAY = 30.0


# ─── Robust Streaming SSE Parser ─────────────────────────────────────────────

class SSEParser:
    """
    Robust Server-Sent Events (SSE) parser for streaming LLM responses.
    Handles:
      - Split TCP packet buffers across chunk boundaries
      - Normalization of CRLF (\r\n), LF (\n), and bare CR (\r)
      - Concatenation of multi-line 'data:' payloads for single events per WHATWG SSE spec
      - Stripping of SSE comments (: keep-alive, : heartbeat, etc.)
      - Dispatches '[DONE]' stream termination sentinel
      - Robust against non-spaced Azure 'data:{"choices":...}' syntax
      - Graceful handling of malformed or non-JSON event payloads
    """
    def __init__(self):
        self._buffer = ""
        self._current_data_lines: List[str] = []

    def feed(self, chunk: Union[str, bytes]) -> List[Dict[str, Any]]:
        """
        Feed raw string or bytes chunk and return list of parsed event dicts.
        When '[DONE]' is encountered, yields {'done': True, 'object': 'chat.completion.chunk.done'}.
        """
        if isinstance(chunk, bytes):
            text = chunk.decode("utf-8", errors="replace")
        else:
            text = str(chunk)

        self._buffer += text
        normalized = self._buffer.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.split("\n")
        # Keep last partial un-terminated line in buffer
        self._buffer = lines.pop()

        events: List[Dict[str, Any]] = []
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                # Empty line: dispatch accumulated event data
                if self._current_data_lines:
                    event_payload = "\n".join(self._current_data_lines)
                    self._current_data_lines = []
                    evt = self._parse_payload(event_payload)
                    if evt:
                        events.append(evt)
                continue

            if trimmed.startswith(":"):
                # SSE heartbeat / comment line - ignore
                continue

            if trimmed.startswith("data:"):
                raw_payload = line[line.index("data:") + 5:]
                # Per SSE specification, strip single leading space if present
                if raw_payload.startswith(" "):
                    raw_payload = raw_payload[1:]

                stripped = raw_payload.strip()
                if stripped == "[DONE]":
                    events.append({"done": True, "object": "chat.completion.chunk.done"})
                    self._current_data_lines = []
                    continue

                # If it's a self-contained single-line JSON, dispatch immediately
                if stripped.startswith("{") and stripped.endswith("}"):
                    try:
                        data = json.loads(stripped)
                        if isinstance(data, dict):
                            events.append(data)
                            continue
                    except Exception:
                        pass

                self._current_data_lines.append(raw_payload)

        return events

    def _parse_payload(self, payload: str) -> Optional[Dict[str, Any]]:
        trimmed = payload.strip()
        if not trimmed:
            return None
        if trimmed == "[DONE]":
            return {"done": True, "object": "chat.completion.chunk.done"}
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"raw_data": trimmed}

    def close(self) -> List[Dict[str, Any]]:
        """Flush any trailing line left in the buffer upon stream closure."""
        events: List[Dict[str, Any]] = []
        if self._buffer.strip():
            line = self._buffer.strip()
            if line.startswith("data:"):
                raw = line[line.index("data:") + 5:]
                if raw.startswith(" "):
                    raw = raw[1:]
                self._current_data_lines.append(raw)
        self._buffer = ""

        if self._current_data_lines:
            payload = "\n".join(self._current_data_lines)
            self._current_data_lines = []
            evt = self._parse_payload(payload)
            if evt:
                events.append(evt)

        return events


# ─── Stream Chunk Aggregator ──────────────────────────────────────────────────

class StreamChunkAggregator:
    """
    Aggregates streaming SSE chunks into a complete CompletionResponse.
    Tracks:
      - Content text deltas
      - Reasoning content deltas (for DeepSeek R1 / o1 / o3)
      - Tool call deltas (joining chunked function arguments across indices)
      - Usage metadata if returned in stream
      - Finish reason
    """
    def __init__(self, model: str = "", provider: str = ""):
        self.model = model
        self.provider = provider
        self.id = ""
        self.content = ""
        self.reasoning_content = ""
        self.tool_calls: List[Dict[str, Any]] = []
        self._tool_calls_by_index: Dict[int, Dict[str, Any]] = {}
        self.finish_reason: Optional[str] = None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.ttft_ms: Optional[float] = None
        self._start_time = time.monotonic()

    def add_chunk(self, chunk: Union[dict, str]) -> Optional[str]:
        """Process a single SSE chunk and return content delta string if present."""
        if isinstance(chunk, str):
            self.content += chunk
            if self.ttft_ms is None and chunk:
                self.ttft_ms = round((time.monotonic() - self._start_time) * 1000, 2)
            return chunk

        if not isinstance(chunk, dict):
            return None

        if "id" in chunk and not self.id:
            self.id = chunk["id"]
        if "model" in chunk:
            self.model = chunk["model"]

        # Usage metadata chunk (e.g. OpenAI stream_options.include_usage)
        if "usage" in chunk and isinstance(chunk["usage"], dict):
            u = chunk["usage"]
            self.prompt_tokens = u.get("prompt_tokens", self.prompt_tokens)
            self.completion_tokens = u.get("completion_tokens", self.completion_tokens)

        choices = chunk.get("choices")
        if not choices or not isinstance(choices, list):
            return None

        choice = choices[0]
        if not isinstance(choice, dict):
            return None

        if choice.get("finish_reason"):
            self.finish_reason = choice.get("finish_reason")

        delta = choice.get("delta")
        if not delta or not isinstance(delta, dict):
            return None

        # Content text delta
        content_delta = delta.get("content")
        if content_delta:
            self.content += content_delta

        # Reasoning content delta (DeepSeek R1 / o1 / o3)
        reasoning_delta = delta.get("reasoning_content")
        if reasoning_delta:
            self.reasoning_content += reasoning_delta

        if self.ttft_ms is None and (content_delta or reasoning_delta):
            self.ttft_ms = round((time.monotonic() - self._start_time) * 1000, 2)

        # Tool calls chunking
        raw_tools = delta.get("tool_calls")
        if raw_tools and isinstance(raw_tools, list):
            for tc in raw_tools:
                idx = tc.get("index", 0)
                if idx not in self._tool_calls_by_index:
                    self._tool_calls_by_index[idx] = {
                        "id": tc.get("id", ""),
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": tc.get("function", {}).get("name", "") if tc.get("function") else "",
                            "arguments": tc.get("function", {}).get("arguments", "") if tc.get("function") else "",
                        }
                    }
                else:
                    curr = self._tool_calls_by_index[idx]
                    if tc.get("id"):
                        curr["id"] = tc["id"]
                    fn = tc.get("function")
                    if fn:
                        if fn.get("name"):
                            curr["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            curr["function"]["arguments"] += fn["arguments"]

        return content_delta

    def build_response(self, latency_ms: float = 0.0) -> CompletionResponse:
        """Construct consolidated CompletionResponse."""
        if self._tool_calls_by_index:
            self.tool_calls = [self._tool_calls_by_index[i] for i in sorted(self._tool_calls_by_index.keys())]

        return CompletionResponse(
            id=self.id or f"chatcmpl-stream-{secrets.token_hex(8)}",
            model=self.model,
            provider=self.provider,
            content=self.content,
            reasoning_content=self.reasoning_content if self.reasoning_content else None,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens or max(1, len(self.content) // 4),
            latency_ms=latency_ms,
            tool_calls=self.tool_calls if self.tool_calls else None,
        )


# ─── Retry Policies ──────────────────────────────────────────────────────────

class RetryPolicy:
    """Encapsulates retry + delay configuration with exponential backoff and jitter."""
    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        max_delay: float = DEFAULT_MAX_DELAY,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        base = min(self.max_delay, self.retry_delay * (self.backoff_factor ** attempt))
        if self.jitter:
            jittered = base * random.uniform(0.5, 1.5)
            return min(self.max_delay, max(0.01, jittered))
        return base


class SmartRetryState:
    """Tracks retry budget per request."""
    def __init__(self, policy: RetryPolicy):
        self.policy = policy
        self.retries_used = 0

    @property
    def has_budget(self) -> bool:
        return self.retries_used < self.policy.max_retries

    def consume(self):
        self.retries_used += 1

    async def wait_if_needed(self, provider_name: str, has_alt_key: bool):
        """
        Smart wait logic:
          - If another key is available for same provider → no wait, rotate immediately
          - Else if retry budget remains → wait calculated backoff delay with jitter, try next provider
        """
        if has_alt_key:
            logger.info(f"[{provider_name}] Alternative key available — rotating immediately (no delay)")
            return
        if self.has_budget:
            delay = self.policy.calculate_delay(self.retries_used)
            logger.info(
                f"[{provider_name}] No alternative keys. "
                f"Waiting {delay:.2f}s before next provider "
                f"(retry {self.retries_used + 1}/{self.policy.max_retries}, backoff factor {self.policy.backoff_factor})"
            )
            await asyncio.sleep(delay)
            self.consume()


# ─── Stream Resilience Manager ───────────────────────────────────────────────

class StreamResilienceManager:
    """Smart LLM Manager with adaptive retry, key rotation, and stream failover."""

    def __init__(self, router, key_manager, providers: dict):
        self.router = router
        self.key_manager = key_manager
        self.providers = providers

    def _default_policy(self) -> RetryPolicy:
        return RetryPolicy(DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY)

    def _has_alt_key(self, provider: str) -> bool:
        """Returns True if the provider has at least one MORE usable key right now."""
        stats = self.key_manager.key_count(provider)
        return stats["active"] > 0

    # ─── Non-streaming ───────────────────────────────────────────────────

    async def complete(
        self,
        request: CompletionRequest,
        retry_policy: Optional[RetryPolicy] = None,
        strategy: Optional["RoutingStrategy"] = None,
        group: Optional[str] = None,
        key_strategy: str = "round_robin",
        headers: Optional[Dict[str, str]] = None,
    ) -> CompletionResponse:
        """
        Smart completion with adaptive retry.
        - Rotates keys within a provider before falling back.
        - Supports key_strategy: "round_robin" or "least_used".
        - Waits retry_delay only when no more keys exist for current provider.
        - Forwards dynamic headers to upstream provider.
        """
        policy = retry_policy or self._default_policy()
        state = SmartRetryState(policy)
        effective_strategy = strategy or getattr(self.router, "strategy", None)
        if group and request.model and group != request.model:
            primary_route = self.router.get_route(request.model, strategy=strategy, messages=request.messages)
            group_route = self.router.get_route(group, strategy=strategy, messages=request.messages)
            route = primary_route
            for r in group_route:
                if r not in route:
                    route.append(r)
        else:
            route = self.router.get_route(group or request.model, strategy=strategy, messages=request.messages)
        errors: List[VeloRouteError] = []

        # Speculative Parallel Hedging (pLLM style): race top 2 available candidates concurrently
        is_hedging = (
            effective_strategy is not None
            and (getattr(effective_strategy, "value", effective_strategy) == "hedging")
        )
        if is_hedging and len(route) >= 2:
            hedge_specs = []
            hedged_indices = set()
            for idx, (p_name, m_name) in enumerate(route):
                if p_name not in self.providers:
                    continue
                k = self.key_manager.get_next_key(p_name, strategy=key_strategy)
                if not k:
                    continue
                hedge_specs.append((p_name, m_name, k))
                hedged_indices.add(idx)
                if len(hedge_specs) == 2:
                    break

            if len(hedge_specs) == 2:
                async def _run_hedged(p_name: str, m_name: str, api_key: str) -> Tuple[str, str, CompletionResponse, float]:
                    prov = self.providers[p_name]
                    req_copy = request.model_copy(deep=True)
                    req_copy.model = m_name or request.model
                    t_start = time.monotonic()
                    resp = await prov.generate(req_copy, api_key, headers=headers)
                    elapsed_ms = (time.monotonic() - t_start) * 1000
                    return p_name, api_key, resp, elapsed_ms

                tasks = {
                    asyncio.create_task(_run_hedged(p_name, m_name, k)): (p_name, k)
                    for p_name, m_name, k in hedge_specs
                }
                pending = set(tasks.keys())
                try:
                    while pending:
                        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                        for finished in done:
                            p_name, api_key = tasks[finished]
                            exc = finished.exception()
                            if exc is None:
                                win_prov, win_key, win_resp, win_lat = finished.result()
                                for loser in pending:
                                    loser.cancel()
                                if pending:
                                    await asyncio.gather(*pending, return_exceptions=True)
                                self.router.record_latency(win_prov, win_lat)
                                self.key_manager.report_success(win_prov, win_key)
                                logger.info(f"[{win_prov}] Hedged winner finished in {win_lat:.0f}ms")
                                return win_resp
                            if isinstance(exc, ContentPolicyError):
                                for rem in pending:
                                    rem.cancel()
                                if pending:
                                    await asyncio.gather(*pending, return_exceptions=True)
                                raise exc
                            if isinstance(exc, AuthenticationError):
                                self.key_manager.report_error(p_name, api_key, "auth")
                            elif isinstance(exc, (RateLimitError, QuotaExceededError)):
                                self.key_manager.report_error(
                                    p_name, api_key, "rate_limit" if isinstance(exc, RateLimitError) else "quota"
                                )
                                self.router.record_latency(p_name, 30000.0)
                            elif isinstance(exc, (ServiceUnavailableError, BadGatewayError, GatewayTimeoutError, InternalServerError, APIConnectionError)):
                                self.key_manager.report_error(p_name, api_key, "server")
                                self.router.record_latency(p_name, 30000.0)
                            errors.append(exc if isinstance(exc, VeloRouteError) else VeloRouteError(str(exc), provider=p_name))
                finally:
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                # Filter out already-hedged single-key candidates if exhausted, or fall through to remaining route
                route = [pair for i, pair in enumerate(route) if i not in hedged_indices]

        for provider_name, model in route:
            if provider_name not in self.providers:
                continue

            provider = self.providers[provider_name]
            keys_tried = 0
            max_keys_to_try = max(policy.max_retries + 1, self.key_manager.key_count(provider_name)["total"])

            while keys_tried < max_keys_to_try:
                key = self.key_manager.get_next_key(provider_name, strategy=key_strategy)
                if not key:
                    break
                keys_tried += 1

                req = request.model_copy(deep=True)
                req.model = model or request.model

                try:
                    t0 = time.monotonic()
                    response = await provider.generate(req, key, headers=headers)
                    latency = (time.monotonic() - t0) * 1000
                    self.router.record_latency(provider_name, latency)
                    self.key_manager.report_success(provider_name, key)
                    logger.info(f"[{provider_name}] Success in {latency:.0f}ms")
                    return response

                except ContentPolicyError:
                    raise  # Never retry content policy violations

                except NotFoundError as e:
                    # Model not found on this provider - don't waste other keys on same provider!
                    logger.warning(f"[{provider_name}] Model {req.model} not found (404). Failing over to next provider.")
                    errors.append(e)
                    break

                except AuthenticationError as e:
                    self.key_manager.report_error(provider_name, key, "auth")
                    errors.append(e)
                    continue

                except PermissionDeniedError as e:
                    # Model restriction or subscription required for this specific model - key is NOT invalid!
                    logger.warning(f"[{provider_name}] Model {req.model} restricted/permission denied: {e}")
                    errors.append(e)
                    break

                except (BadRequestError, ContextWindowError) as e:
                    # Request-level / client prompt error - provider key is healthy!
                    errors.append(e)
                    break

                except (RateLimitError, QuotaExceededError) as e:
                    err_type = "rate_limit" if isinstance(e, RateLimitError) else "quota"
                    self.key_manager.report_error(provider_name, key, err_type)
                    self.router.record_latency(provider_name, 30000.0)
                    errors.append(e)
                    has_alt = self._has_alt_key(provider_name)
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break

                except (ServiceUnavailableError, BadGatewayError, GatewayTimeoutError, InternalServerError, APIConnectionError) as e:
                    self.key_manager.report_error(provider_name, key, "server")
                    self.router.record_latency(provider_name, 30000.0)
                    errors.append(e)
                    has_alt = self._has_alt_key(provider_name)
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break

                except VeloRouteError as e:
                    self.key_manager.report_error(provider_name, key, "server")
                    self.router.record_latency(provider_name, 30000.0)
                    errors.append(e)
                    has_alt = self._has_alt_key(provider_name)
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break

            if not state.has_budget and errors:
                logger.warning("Retry budget exhausted — skipping remaining providers.")
                break

        raise AllProvidersFailedError(errors)

# ─── Streaming ─────────────────────────────────────────────────────────────

    async def safe_stream_events(
        self,
        request: CompletionRequest,
        stop_event: Optional[asyncio.Event] = None,
        retry_policy: Optional[RetryPolicy] = None,
        strategy: Optional["RoutingStrategy"] = None,
        group: Optional[str] = None,
        key_strategy: str = "round_robin",
        headers: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Smart resilient streaming yielding structured event dicts.
        - Rotates keys within a provider before falling back.
        - Forwards dynamic headers to upstream provider.
        - Re-injects partial response context on failover.
        """
        policy = retry_policy or self._default_policy()
        state = SmartRetryState(policy)
        if group and request.model and group != request.model:
            primary_route = self.router.get_route(request.model, strategy=strategy, messages=request.messages)
            group_route = self.router.get_route(group, strategy=strategy, messages=request.messages)
            route = primary_route
            for r in group_route:
                if r not in route:
                    route.append(r)
        else:
            route = self.router.get_route(group or request.model, strategy=strategy, messages=request.messages)
        errors: List[VeloRouteError] = []
        generated_so_far = ""
        _stopped = False
        ttft_ms: Optional[float] = None
        stream_start_ts = time.monotonic()

        for provider_name, model in route:
            if provider_name not in self.providers:
                continue

            provider = self.providers[provider_name]
            keys_tried = 0
            max_keys_to_try = max(policy.max_retries + 1, self.key_manager.key_count(provider_name)["total"])

            while keys_tried < max_keys_to_try:
                key = self.key_manager.get_next_key(provider_name, strategy=key_strategy)

                if not key:
                    break
                keys_tried += 1

                req = request.model_copy(deep=True)
                req.model = model or request.model
                req.stream = True

                # Inject partial context on failover
                if generated_so_far:
                    req.messages = list(request.messages) + [
                        Message(role="assistant", content=generated_so_far),
                        Message(
                            role="user",
                            content="Continue your response exactly from where you stopped. Do not repeat anything.",
                        ),
                    ]

                t0 = time.monotonic()
                try:
                    logger.info(
                        f"[{provider_name}] Streaming events model={req.model} "
                        f"key#{keys_tried} "
                        f"retry_budget={policy.max_retries - state.retries_used} "
                        f"chars_so_far={len(generated_so_far)}"
                    )

                    if hasattr(provider, "generate_stream_events"):
                        stream_source = provider.generate_stream_events(req, key, headers=headers)
                    else:
                        async def _wrap():
                            async for chunk in provider.generate_stream(req, key, headers=headers):
                                yield {"type": "content", "text": chunk}
                        stream_source = _wrap()

                    async for event in stream_source:
                        if stop_event and stop_event.is_set():
                            logger.info(f"[{provider_name}] Stopped via stop_event after {len(generated_so_far)} chars.")
                            _stopped = True
                            return

                        if ttft_ms is None:
                            ttft_ms = round((time.monotonic() - stream_start_ts) * 1000, 2)

                        if isinstance(event, dict):
                            if event.get("type") == "content":
                                generated_so_far += (event.get("text") or "")
                            event.setdefault("provider", provider_name)
                            event.setdefault("model", req.model)
                            event["fallback_used"] = (provider_name != route[0][0]) if route else False
                            event["retries"] = state.retries_used
                            event["ttft_ms"] = ttft_ms
                            try:
                                yield event
                            except GeneratorExit:
                                logger.info(f"[{provider_name}] GeneratorExit after {len(generated_so_far)} chars.")
                                _stopped = True
                                return
                        else:
                            generated_so_far += str(event)
                            try:
                                yield {
                                    "type": "content",
                                    "text": str(event),
                                    "provider": provider_name,
                                    "model": req.model,
                                    "fallback_used": (provider_name != route[0][0]) if route else False,
                                    "retries": state.retries_used,
                                    "ttft_ms": ttft_ms,
                                }
                            except GeneratorExit:
                                _stopped = True
                                return

                    latency = (time.monotonic() - t0) * 1000
                    self.router.record_latency(provider_name, latency)
                    self.key_manager.report_success(provider_name, key)
                    return  # full stream complete

                except asyncio.CancelledError:
                    _stopped = True
                    raise

                except ContentPolicyError:
                    raise

                except NotFoundError as e:
                    logger.warning(f"[{provider_name}] Model {req.model} not found (404) during stream. Failing over.")
                    errors.append(e)
                    break

                except AuthenticationError as e:
                    self.key_manager.report_error(provider_name, key, "auth")
                    errors.append(e)
                    continue

                except PermissionDeniedError as e:
                    logger.warning(f"[{provider_name}] Model {req.model} restricted/permission denied: {e}")
                    errors.append(e)
                    break

                except (BadRequestError, ContextWindowError) as e:
                    errors.append(e)
                    break

                except (RateLimitError, QuotaExceededError) as e:
                    err_type = "rate_limit" if isinstance(e, RateLimitError) else "quota"
                    self.key_manager.report_error(provider_name, key, err_type)
                    self.router.record_latency(provider_name, 30000.0)
                    errors.append(e)
                    has_alt = self._has_alt_key(provider_name)
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break

                except (ServiceUnavailableError, BadGatewayError, GatewayTimeoutError, InternalServerError, APIConnectionError) as e:
                    self.key_manager.report_error(provider_name, key, "server")
                    self.router.record_latency(provider_name, 30000.0)
                    errors.append(e)
                    has_alt = self._has_alt_key(provider_name)
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break

                except VeloRouteError as e:
                    self.key_manager.report_error(provider_name, key, "server")
                    self.router.record_latency(provider_name, 30000.0)
                    errors.append(e)
                    if generated_so_far:
                        logger.warning(
                            f"[{provider_name}] Stream interrupted at {len(generated_so_far)} chars – failing over with context."
                        )
                    has_alt = self._has_alt_key(provider_name)
                    await state.wait_if_needed(provider_name, has_alt)
                    if has_alt:
                        continue
                    break

                except Exception as e:
                    logger.error(f"[{provider_name}] Unexpected: {e}")
                    self.router.record_latency(provider_name, 30000.0)
                    errors.append(VeloRouteError(str(e), provider=provider_name))
                    break

            if not state.has_budget and errors:
                break

        if not _stopped:
            if not generated_so_far:
                raise AllProvidersFailedError(errors)

    async def safe_stream(
        self,
        request: CompletionRequest,
        stop_event: Optional[asyncio.Event] = None,
        retry_policy: Optional[RetryPolicy] = None,
        strategy: Optional["RoutingStrategy"] = None,
        group: Optional[str] = None,
        key_strategy: str = "round_robin",
        headers: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Convenience text-only generator wrapping safe_stream_events."""
        async for event in self.safe_stream_events(
            request=request,
            stop_event=stop_event,
            retry_policy=retry_policy,
            strategy=strategy,
            group=group,
            key_strategy=key_strategy,
            headers=headers,
        ):
            if event.get("type") == "content" and event.get("text"):
                yield event["text"]
