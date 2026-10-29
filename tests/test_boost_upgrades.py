import os
import sys
import unittest
import asyncio
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

# Ensure package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from llmcycle import (
    LLMCycle,
    LLMCycleError,
    RateLimitError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    BadRequestError,
    ProviderError,
    InternalServerError,
    BadGatewayError,
    ServiceUnavailableError,
    GatewayTimeoutError,
    QuotaExceededError,
    ContentPolicyError,
    ContextWindowError,
    SSEParser,
    StreamChunkAggregator,
    count_tokens,
    count_message_tokens,
    get_model_pricing,
    get_model_context_window,
    extract_forward_headers,
    merge_request_headers,
    parse_model,
    MODEL_PRICING,
    CONTEXT_WINDOWS,
)
from llmcycle.core.errors import classify_http_error
from llmcycle.schema import CompletionRequest, Message
from llmcycle.providers.openai_compatible import OpenAICompatibleProvider
from starlette.testclient import TestClient
from llmcycle.ui.app import app
from llmcycle.ui.routes.deps import SESSION_TOKEN, llm_client


class TestModelPricingAndContextWindows(unittest.TestCase):
    def test_pricing_lookup_exact(self):
        # Modern flagship and reasoning models
        self.assertIsNotNone(get_model_pricing("gpt-4o"))
        self.assertIsNotNone(get_model_pricing("o3-mini"))
        self.assertIsNotNone(get_model_pricing("claude-3-7-sonnet"))
        self.assertIsNotNone(get_model_pricing("gemini-2.0-flash"))
        self.assertIsNotNone(get_model_pricing("deepseek-r1"))
        self.assertIsNotNone(get_model_pricing("deepseek-v3"))
        self.assertIsNotNone(get_model_pricing("llama-3.3-70b"))
        self.assertIsNotNone(get_model_pricing("codestral"))
        self.assertIsNotNone(get_model_pricing("sonar-pro"))

    def test_pricing_lookup_provider_prefix_and_date_suffix(self):
        # Strips prefix
        p1 = get_model_pricing("openai/gpt-4o")
        self.assertEqual(p1, get_model_pricing("gpt-4o"))

        p2 = get_model_pricing("anthropic/claude-3-7-sonnet")
        self.assertEqual(p2, get_model_pricing("claude-3-7-sonnet"))

        # Strips date suffix
        p_date = get_model_pricing("gpt-4o-2024-08-06")
        self.assertIsNotNone(p_date)
        self.assertEqual(p_date["input"], 0.0025)

        p_o1_date = get_model_pricing("o1-2024-12-17")
        self.assertIsNotNone(p_o1_date)
        self.assertEqual(p_o1_date["input"], 0.015)

    def test_pricing_longest_match_no_substring_collision(self):
        # gpt-4o-mini-preview must match gpt-4o-mini ($0.00015), NOT gpt-4o ($0.0025)
        p_mini = get_model_pricing("gpt-4o-mini-preview")
        self.assertIsNotNone(p_mini)
        self.assertEqual(p_mini["input"], 0.00015)

        # o1-mini-custom must match o1-mini ($0.003), NOT o1 ($0.015)
        p_o1_mini = get_model_pricing("o1-mini-custom")
        self.assertIsNotNone(p_o1_mini)
        self.assertEqual(p_o1_mini["input"], 0.003)

        # claude-3-7-sonnet-20250219 date strip
        p_c37 = get_model_pricing("claude-3-7-sonnet-20250219")
        self.assertIsNotNone(p_c37)
        self.assertEqual(p_c37["input"], 0.003)

    def test_context_window_lookup(self):
        # 1M / 2M context windows
        self.assertGreaterEqual(get_model_context_window("gemini-2.0-flash"), 1_000_000)
        self.assertGreaterEqual(get_model_context_window("gemini-1.5-pro"), 2_000_000)
        # 200k context windows
        self.assertEqual(get_model_context_window("o1"), 200_000)
        self.assertEqual(get_model_context_window("o3-mini"), 200_000)
        self.assertEqual(get_model_context_window("claude-3-7-sonnet"), 200_000)
        # 128k context windows
        self.assertEqual(get_model_context_window("gpt-4o"), 128_000)
        self.assertEqual(get_model_context_window("llama-3.3-70b"), 128_000)
        self.assertEqual(get_model_context_window("llama-3.1-405b"), 128_000)
        # Fallback default for unknown
        self.assertEqual(get_model_context_window("unknown-custom-model-x"), 128_000)


class TestTokenCountingEngine(unittest.TestCase):
    def test_count_tokens_empty(self):
        self.assertEqual(count_tokens(""), 0)
        self.assertEqual(count_tokens(None), 0)
        self.assertEqual(count_tokens([]), 0)

    def test_count_tokens_english_text(self):
        text = "The quick brown fox jumps over the lazy dog."
        tokens = count_tokens(text)
        self.assertGreater(tokens, 5)
        self.assertLess(tokens, 20)

    def test_count_tokens_cjk_multilingual(self):
        # In BPE tokenizers, CJK characters consume ~1.5 - 2 tokens per character
        cjk_text = "人工智能模型与深度学习"  # 11 CJK chars
        tokens = count_tokens(cjk_text)
        self.assertGreaterEqual(tokens, 11)

    def test_count_tokens_multimodal_dict(self):
        img_low = {"type": "image_url", "image_url": {"url": "https://example.com/img.png", "detail": "low"}}
        self.assertEqual(count_tokens(img_low), 85)

        img_high = {"type": "image_url", "image_url": {"url": "https://example.com/img.png", "detail": "high"}}
        self.assertEqual(count_tokens(img_high), 255)

        txt_part = {"type": "text", "text": "Describe this image in detail please."}
        self.assertGreater(count_tokens(txt_part), 4)

    def test_count_message_tokens_format(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello world!"},
        ]
        # Standard: 3 tokens per message (6) + system text + user text + role tokens + 3 reply priming
        count = count_message_tokens(messages, model="gpt-4o")
        self.assertGreater(count, 15)

    def test_count_message_tokens_with_tool_calls(self):
        msgs = [{
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_abc123",
                "type": "function",
                "function": {"name": "calculate_tax", "arguments": '{"income": 120000, "state": "CA"}'}
            }]
        }]
        tokens = count_message_tokens(msgs, model="gpt-4o")
        self.assertGreater(tokens, 15)


class TestDynamicRequestHeaders(unittest.TestCase):
    def test_hop_by_hop_and_auth_stripping(self):
        incoming = {
            "Host": "api.llmcycle.com",
            "Connection": "keep-alive",
            "Content-Length": "1234",
            "Cookie": "session=abc",
            "Accept-Encoding": "gzip, deflate",
            "Authorization": "Bearer proxy-key-to-strip",
            "x-api-key": "virtual-gateway-key-to-strip",
            "User-Agent": "MyLLMApp/1.0",
            "x-request-id": "req-999",
            "anthropic-version": "2023-06-01",
            "x-custom-tenant": "tenant-42",
        }
        forwarded = extract_forward_headers(incoming, strip_auth=True)
        # Stripped
        self.assertNotIn("Host", forwarded)
        self.assertNotIn("Connection", forwarded)
        self.assertNotIn("Content-Length", forwarded)
        self.assertNotIn("Cookie", forwarded)
        self.assertNotIn("Accept-Encoding", forwarded)
        self.assertNotIn("Authorization", forwarded)
        self.assertNotIn("x-api-key", forwarded)

        # Retained
        self.assertIn("User-Agent", forwarded)
        self.assertEqual(forwarded["User-Agent"], "MyLLMApp/1.0")
        self.assertIn("x-request-id", forwarded)
        self.assertEqual(forwarded["x-request-id"], "req-999")
        self.assertIn("anthropic-version", forwarded)
        self.assertEqual(forwarded["anthropic-version"], "2023-06-01")
        self.assertIn("x-custom-tenant", forwarded)

    def test_merge_request_headers(self):
        base = {
            "Authorization": "Bearer real-provider-key",
            "Content-Type": "application/json",
        }
        extra = {
            "Authorization": "Bearer bad-override",  # Must not override real Authorization
            "Host": "bad.host",                     # Must not include hop-by-hop
            "x-trace-id": "trace-101",
        }
        merged = merge_request_headers(base, extra)
        self.assertEqual(merged["Authorization"], "Bearer real-provider-key")
        self.assertNotIn("Host", merged)
        self.assertEqual(merged["x-trace-id"], "trace-101")
        self.assertEqual(merged["Content-Type"], "application/json")

    def test_merge_request_headers_case_insensitive_auth(self):
        base = {"authorization": "Bearer real-lower-key", "Content-Type": "application/json"}
        extra = {"authorization": "Bearer bad-override", "Authorization": "Bearer bad-upper-override"}
        merged = merge_request_headers(base, extra)
        self.assertEqual(merged["authorization"], "Bearer real-lower-key")
        self.assertNotIn("Authorization", merged)


class TestComprehensiveErrorMapping(unittest.TestCase):
    def test_status_401_authentication(self):
        err = classify_http_error(401, '{"error": {"message": "Invalid API key provided"}}', "openai", "gpt-4o")
        self.assertIsInstance(err, AuthenticationError)
        self.assertEqual(err.status_code, 401)
        self.assertIn("Invalid API key", str(err))

    def test_status_403_permission_denied(self):
        err = classify_http_error(403, '{"error": {"message": "Country, region, or territory not supported"}}', "openai", "gpt-4o")
        self.assertIsInstance(err, PermissionDeniedError)
        self.assertEqual(err.status_code, 403)

    def test_status_404_not_found(self):
        err = classify_http_error(404, '{"error": {"message": "The model gpt-5 does not exist"}}', "openai", "gpt-5")
        self.assertIsInstance(err, NotFoundError)
        self.assertEqual(err.status_code, 404)

    def test_status_429_rate_limit(self):
        err = classify_http_error(429, '{"error": {"message": "Rate limit reached for requests per min"}}', "groq", "llama-3.3-70b")
        self.assertIsInstance(err, RateLimitError)
        self.assertEqual(err.status_code, 429)

    def test_status_429_quota_exceeded(self):
        err = classify_http_error(429, '{"error": {"message": "You exceeded your current quota, please check your plan and billing details"}}', "openai", "gpt-4o")
        self.assertIsInstance(err, QuotaExceededError)

    def test_status_402_payment_required(self):
        err = classify_http_error(402, '{"error": "insufficient_quota"}', "deepseek", "deepseek-chat")
        self.assertIsInstance(err, QuotaExceededError)
        self.assertEqual(err.status_code, 402)

    def test_status_400_context_window_exceeded(self):
        body = '{"error": {"message": "This model\'s maximum context length is 128000 tokens, however you requested 140000 tokens.", "type": "invalid_request_error", "code": "context_length_exceeded"}}'
        err = classify_http_error(400, body, "openai", "gpt-4o")
        self.assertIsInstance(err, ContextWindowError)

    def test_status_400_content_policy(self):
        body = '{"error": {"message": "The response was blocked by safety filters due to content policy violation"}}'
        err = classify_http_error(400, body, "gemini", "gemini-1.5-flash")
        self.assertIsInstance(err, ContentPolicyError)

    def test_status_400_bad_request(self):
        body = '{"error": {"message": "Unrecognized parameter: foo"}}'
        err = classify_http_error(400, body, "openai", "gpt-4o")
        self.assertIsInstance(err, BadRequestError)
        self.assertEqual(err.status_code, 400)

    def test_status_429_rate_limit_violation_string(self):
        # Must NOT be misclassified as ContentPolicyError
        err = classify_http_error(429, '{"error": {"message": "Rate limit violation: exceeded 500 RPM"}}', "openai", "gpt-4o")
        self.assertIsInstance(err, RateLimitError)
        self.assertEqual(err.status_code, 429)

    def test_status_400_parameter_violation_string(self):
        # Must be BadRequestError, not ContentPolicyError
        err = classify_http_error(400, '{"error": {"message": "Parameter n violated range constraint [1, 10]"}}', "openai", "gpt-4o")
        self.assertIsInstance(err, BadRequestError)
        self.assertEqual(err.status_code, 400)

    def test_status_401_with_billing_words(self):
        # 401 must be AuthenticationError even if message mentions billing
        err = classify_http_error(401, '{"error": {"message": "Unauthorized billing account"}}', "openai", "gpt-4o")
        self.assertIsInstance(err, AuthenticationError)
        self.assertEqual(err.status_code, 401)

    def test_status_500_internal_error(self):
        err = classify_http_error(500, "Internal Server Error", "anthropic", "claude-3-5-sonnet")
        self.assertIsInstance(err, InternalServerError)
        self.assertEqual(err.status_code, 500)

    def test_status_502_bad_gateway(self):
        err = classify_http_error(502, "Bad Gateway", "together", "llama-3-70b")
        self.assertIsInstance(err, BadGatewayError)

    def test_status_503_service_unavailable(self):
        err = classify_http_error(503, "Service Unavailable", "mistral", "mistral-large")
        self.assertIsInstance(err, ServiceUnavailableError)

    def test_status_529_anthropic_overloaded(self):
        err = classify_http_error(529, '{"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}', "anthropic", "claude-3-5-sonnet")
        self.assertIsInstance(err, ServiceUnavailableError)

    def test_status_504_gateway_timeout(self):
        err = classify_http_error(504, "Gateway Timeout", "groq", "llama-3.1-70b")
        self.assertIsInstance(err, GatewayTimeoutError)


class TestStreamingSSEParserAndAggregator(unittest.TestCase):
    def test_sse_parser_split_and_crlf(self):
        parser = SSEParser()
        # Feed partial chunk
        chunk1 = "data: {\"choices\": [{\"delta\": {\"c"
        events1 = parser.feed(chunk1)
        self.assertEqual(len(events1), 0)

        # Feed completion with CRLF
        chunk2 = "ontent\": \"Hello \"}}]}\r\n\r\n"
        events2 = parser.feed(chunk2)
        self.assertEqual(len(events2), 1)
        self.assertEqual(events2[0]["choices"][0]["delta"]["content"], "Hello ")

    def test_sse_parser_comments_and_done(self):
        parser = SSEParser()
        raw = (
            ": keepalive heartbeat\n\n"
            "data: {\"choices\": [{\"delta\": {\"content\": \"World!\"}}]}\n\n"
            "data: [DONE]\n\n"
        )
        events = parser.feed(raw)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["choices"][0]["delta"]["content"], "World!")
        self.assertTrue(events[1].get("done"))

    def test_sse_parser_multiline_events_whatwg_spec(self):
        parser = SSEParser()
        # WHATWG SSE specification: multiple data lines for same event dispatched on empty line
        chunk1 = "data: {\n"
        chunk2 = 'data: "choices": [{"delta": {"content": "multi-line SSE"}}]}\n\n'
        events1 = parser.feed(chunk1)
        self.assertEqual(len(events1), 0)  # Buffered until empty line

        events2 = parser.feed(chunk2)
        self.assertEqual(len(events2), 1)
        self.assertEqual(events2[0]["choices"][0]["delta"]["content"], "multi-line SSE")

    def test_sse_parser_no_space_data_prefix(self):
        parser = SSEParser()
        # Azure sometimes emits data:{"choices":...}
        raw = "data:{\"choices\": [{\"delta\": {\"content\": \"Azure test\"}}]}\n\n"
        events = parser.feed(raw)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["choices"][0]["delta"]["content"], "Azure test")

    def test_stream_chunk_aggregator_text_and_reasoning(self):
        agg = StreamChunkAggregator(model="deepseek-r1", provider="deepseek")
        chunk1 = {
            "id": "chatcmpl-test",
            "choices": [{"delta": {"reasoning_content": "Thinking about math... "}, "finish_reason": None}]
        }
        chunk2 = {
            "choices": [{"delta": {"reasoning_content": "Done thinking.", "content": "The answer "}, "finish_reason": None}]
        }
        chunk3 = {
            "choices": [{"delta": {"content": "is 42."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8}
        }

        agg.add_chunk(chunk1)
        agg.add_chunk(chunk2)
        agg.add_chunk(chunk3)

        self.assertEqual(agg.reasoning_content, "Thinking about math... Done thinking.")
        self.assertEqual(agg.content, "The answer is 42.")
        self.assertEqual(agg.finish_reason, "stop")
        self.assertEqual(agg.prompt_tokens, 10)
        self.assertEqual(agg.completion_tokens, 8)

        resp = agg.build_response(latency_ms=120.0)
        self.assertEqual(resp.content, "The answer is 42.")
        self.assertEqual(resp.latency_ms, 120.0)

    def test_stream_chunk_aggregator_tool_calls(self):
        agg = StreamChunkAggregator(model="gpt-4o", provider="openai")
        # Tool call chunk 1
        c1 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": "{\"loc"}
                    }]
                }
            }]
        }
        # Tool call chunk 2
        c2 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": "ation\": \"Paris\"}"}
                    }]
                }
            }]
        }
        agg.add_chunk(c1)
        agg.add_chunk(c2)
        resp = agg.build_response()
        self.assertIsNotNone(resp.tool_calls)
        self.assertEqual(len(resp.tool_calls), 1)
        self.assertEqual(resp.tool_calls[0]["function"]["name"], "get_weather")
        self.assertEqual(resp.tool_calls[0]["function"]["arguments"], '{"location": "Paris"}')


class TestProviderPingAndHealth(unittest.TestCase):
    def test_provider_ping_success(self):
        async def _run():
            provider = OpenAICompatibleProvider("https://mock.api.com/v1", provider_name="mockprov")
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_post.return_value = mock_resp

                res = await provider.ping("sk-test", model="mock-model")
                self.assertTrue(res["healthy"])
                self.assertEqual(res["status_code"], 200)
                self.assertGreaterEqual(res["latency_ms"], 0)
        asyncio.run(_run())

    def test_provider_ping_auth_failure(self):
        async def _run():
            provider = OpenAICompatibleProvider("https://mock.api.com/v1", provider_name="mockprov")
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 401
                mock_resp.text = '{"error": {"message": "Invalid API Key"}}'
                mock_post.return_value = mock_resp

                res = await provider.ping("sk-test", model="mock-model")
                self.assertFalse(res["healthy"])
                self.assertEqual(res["status_code"], 401)
                self.assertEqual(res["error_type"], "AuthenticationError")
        asyncio.run(_run())

    def test_client_ping_provider_and_ping_all(self):
        async def _run():
            client = LLMCycle()
            client.add_provider("testprov", ["sk-test-key"])
            with patch.object(client._providers["testprov"], "ping", new_callable=AsyncMock) as mock_p:
                mock_p.return_value = {
                    "healthy": True,
                    "latency_ms": 45.2,
                    "provider": "testprov",
                    "status_code": 200
                }
                res = await client.ping_provider("testprov")
                self.assertTrue(res["healthy"])
                self.assertEqual(res["latency_ms"], 45.2)

                all_res = await client.ping_all_providers()
                self.assertIn("testprov", all_res)
                self.assertTrue(all_res["testprov"]["healthy"])
        asyncio.run(_run())

    def test_ping_provider_recovers_disabled_key(self):
        async def _run():
            client = LLMCycle()
            client.add_provider("mockprov", ["sk-disabled-key"], "https://mock.api")
            client.key_manager.report_error("mockprov", "sk-disabled-key", "auth")
            # Key is invalid initially
            self.assertEqual(client.key_manager.key_count("mockprov")["active"], 0)

            with patch.object(client._providers["mockprov"], "ping", new_callable=AsyncMock) as mock_p:
                mock_p.return_value = {
                    "healthy": True,
                    "latency_ms": 55.0,
                    "provider": "mockprov",
                    "status_code": 200
                }
                res = await client.ping_provider("mockprov")
                self.assertTrue(res["healthy"])
                # Key must auto-recover to active
                self.assertEqual(client.key_manager.key_count("mockprov")["active"], 1)
        asyncio.run(_run())

    def test_complete_and_stream_with_message_objects(self):
        async def _run():
            client = LLMCycle()
            client.add_provider("testprov", ["sk-k1"], "https://mock.api")
            with patch.object(client._providers["testprov"], "generate", new_callable=AsyncMock) as mock_gen:
                from llmcycle.schema import CompletionResponse
                mock_gen.return_value = CompletionResponse(
                    id="resp-1", model="test-m", provider="testprov", content="Hello!",
                    reasoning_content="Reasoning trace",
                )
                resp = await client.complete(
                    "testprov/test-m",
                    messages=[
                        Message(role="system", content="System instruction"),
                        Message(role="user", content="User message"),
                    ]
                )
                self.assertEqual(resp.content, "Hello!")
                self.assertEqual(resp.reasoning_content, "Reasoning trace")
        asyncio.run(_run())


class TestFastAPIPingAndProxyEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        llm_client.add_provider("probe_provider", ["sk-probe-key"])

    def test_ping_provider_endpoint(self):
        with patch.object(llm_client._providers["probe_provider"], "ping", new_callable=AsyncMock) as mock_p:
            mock_p.return_value = {
                "healthy": True,
                "latency_ms": 32.5,
                "provider": "probe_provider",
                "status_code": 200
            }
            res = self.client.post("/api/v1/providers/probe_provider/ping", headers=self.headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["healthy"])
            self.assertEqual(data["latency_ms"], 32.5)

    def test_ping_all_providers_endpoint(self):
        with patch.object(llm_client, "ping_all_providers", new_callable=AsyncMock) as mock_all:
            mock_all.return_value = {
                "probe_provider": {"healthy": True, "latency_ms": 28.0, "status_code": 200}
            }
            res = self.client.post("/api/v1/providers/ping_all", headers=self.headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("probe_provider", data)


if __name__ == "__main__":
    unittest.main()
