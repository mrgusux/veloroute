"""
Comprehensive test suite verifying cutting-edge LLM gateway and router upgrades:
1. RouteLLM Complexity-based routing and scoring (lm-sys/RouteLLM pattern)
2. MCP Model Context Protocol JSON-RPC 2.0 and REST endpoints (enkryptai/IBM/AshrafMd-1 patterns)
3. Helicone/GPTCache cache controls, bypass, and response headers
4. Portkey/Bifrost request tagging, trace metadata, and dynamic routing overrides
5. Streaming Time-to-First-Token (TTFT) metrics and StreamEvent tracking
6. Upgraded 2025/2026 model pricing and context window catalog
"""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from veloroute import (
    VeloRoute,
    ComplexityEvaluator,
    ComplexityPair,
    MCPRegistry,
    MCPTool,
    MCPCallResult,
    RoutingStrategy,
)
from veloroute.schema import CompletionResponse, StreamEvent
from veloroute.core.stream import StreamChunkAggregator
from veloroute.ui.app import app
from veloroute.ui.routes.deps import llm_client
from veloroute.utils import DEFAULT_PRICING, DEFAULT_CONTEXT_WINDOWS


class TestComplexityRouting(unittest.TestCase):
    def setUp(self):
        self.evaluator = ComplexityEvaluator()

    def test_simple_prompt_scores_low(self):
        simple_prompts = [
            "Hi",
            "Hello there!",
            "Thank you very much",
            "What is your name?",
            "Good morning!",
        ]
        for p in simple_prompts:
            score = self.evaluator.evaluate(p)
            self.assertLess(
                score,
                0.35,
                f"Simple prompt '{p}' scored {score:.3f}, expected < 0.35",
            )

    def test_complex_prompt_scores_high(self):
        complex_prompts = [
            "Write a Python function implementing Dijkstra's algorithm using a min-heap priority queue, and analyze its step-by-step computational complexity.",
            "Can you provide a rigorous mathematical proof by contradiction that the square root of 2 is irrational?",
            "Optimize this recursive backtracking algorithm using memoization and dynamic programming: def solve(n, k): ...",
            "Explain the architecture of a multi-head self-attention layer in a Transformer model, step-by-step with tensor dimensions.",
        ]
        for p in complex_prompts:
            score = self.evaluator.evaluate(p)
            self.assertGreater(
                score,
                0.40,
                f"Complex prompt scored {score:.3f}, expected > 0.40",
            )

    def test_messages_structure_evaluation(self):
        # Multi-turn conversation with code and system prompt
        messages = [
            {"role": "system", "content": "You are an expert compiler engineer."},
            {"role": "user", "content": "How do register allocation algorithms like graph coloring work?"},
            {"role": "assistant", "content": "Graph coloring builds an interference graph where nodes are variables..."},
            {"role": "user", "content": "Can you implement the Chaitin-Briggs allocator with spilling heuristics in C++?"},
        ]
        score = self.evaluator.evaluate(messages)
        self.assertGreater(score, 0.45)

    def test_model_router_complexity_routing(self):
        client = VeloRoute()
        # Register complexity pair: threshold 0.50
        client.router.register_complexity_pair(
            "my-smart-router",
            fast_model="groq/llama-3.1-8b",
            strong_model="openai/gpt-4o",
            threshold=0.50,
        )

        # Simple prompt routes to fast-model
        simple_route = client.router.get_route(
            "my-smart-router",
            prompt="Hello!",
        )
        self.assertEqual(simple_route[0], ("groq", "llama-3.1-8b"))

        # Complex prompt routes to strong-model
        complex_prompt = (
            "Write a multi-threaded C++ program using atomic compare-and-swap "
            "to implement a lock-free queue with memory fences and hazard pointers."
        )
        complex_route = client.router.get_route(
            "my-smart-router",
            prompt=complex_prompt,
        )
        self.assertEqual(complex_route[0], ("openai", "gpt-4o"))

    def test_routellm_pattern_syntax(self):
        # Test RouteLLM pattern router-complexity-<threshold>
        client = VeloRoute()
        client.router.register_complexity_pair(
            "default",
            fast_model="groq/llama-3.1-8b",
            strong_model="openai/gpt-4o",
            threshold=0.5,
        )

        # RouteLLM pattern: router-complexity-0.30 with simple prompt
        route = client.router.get_route(
            "router-complexity-0.30",
            prompt="Hello there",
        )
        self.assertEqual(route[0], ("groq", "llama-3.1-8b"))

    def test_complexity_pair_serialization(self):
        client = VeloRoute()
        client.router.register_complexity_pair(
            "agent-pair",
            fast_model="openai/gpt-4o-mini",
            strong_model="openai/gpt-4o",
            threshold=0.42,
        )
        data = client.router.to_dict()
        self.assertIn("complexity_pairs", data)
        self.assertEqual(data["complexity_pairs"]["agent-pair"]["threshold"], 0.42)

        new_client = VeloRoute()
        new_client.router.from_dict(data)
        pair = new_client.router.get_complexity_pair("agent-pair")
        self.assertIsNotNone(pair)
        self.assertEqual(pair.threshold, 0.42)
        self.assertEqual(pair.weak_model, "openai/gpt-4o-mini")
        self.assertEqual(pair.strong_model, "openai/gpt-4o")

    def test_multimodal_and_none_text_complexity_resilience(self):
        # Must not raise TypeError when text is None
        score_none = self.evaluator.evaluate(
            messages=[{"role": "user", "content": [{"type": "text", "text": None}]}]
        )
        self.assertIsInstance(score_none, float)
        self.assertEqual(score_none, 0.1)

        # Content is None (e.g. tool call message)
        score_content_none = self.evaluator.evaluate(
            messages=[{"role": "assistant", "content": None}]
        )
        self.assertIsInstance(score_content_none, float)
        self.assertEqual(score_content_none, 0.1)

        # Multimodal image input increases complexity
        score_image = self.evaluator.evaluate(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/diagram.png"}},
                    ],
                }
            ]
        )
        self.assertGreaterEqual(score_image, 0.5)

    def test_complexity_routing_on_groups_and_fallbacks(self):
        client = VeloRoute(
            groups={"hybrid_group": ["openai/gpt-4o", "groq/llama-3.1-8b"]}
        )

        # Simple prompt routes to cheap model in the group
        simple_route = client.router.get_route(
            "hybrid_group",
            strategy=RoutingStrategy.COMPLEXITY,
            prompt="Hi",
        )
        self.assertEqual(simple_route[0], ("groq", "llama-3.1-8b"))

        # Complex reasoning prompt routes to flagship model in the group
        complex_prompt = (
            "Provide a formal mathematical proof by induction that "
            "the sum of the first n cubes equals the square of the nth triangular number."
        )
        complex_route = client.router.get_route(
            "hybrid_group",
            strategy=RoutingStrategy.COMPLEXITY,
            prompt=complex_prompt,
        )
        self.assertEqual(complex_route[0], ("openai", "gpt-4o"))


class TestMCPGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = MCPRegistry()

    async def test_mcp_initialize(self):
        resp = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        })
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        self.assertIn("serverInfo", resp["result"])
        self.assertEqual(resp["result"]["serverInfo"]["name"], "veloroute-mcp-gateway")

    async def test_mcp_ping(self):
        resp = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "ping",
        })
        self.assertEqual(resp["result"], {})

    async def test_mcp_tools_list(self):
        resp = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/list",
        })
        self.assertIn("tools", resp["result"])
        tool_names = [t["name"] for t in resp["result"]["tools"]]
        self.assertIn("calculator", tool_names)
        self.assertIn("veloroute_route_estimate", tool_names)

    async def test_mcp_calculator_call(self):
        resp = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "calculator",
                "arguments": {"expression": "25 * 4 + 7"},
            },
        })
        self.assertIn("result", resp)
        content = resp["result"]["content"]
        self.assertIn("107", content[0]["text"])

    async def test_mcp_custom_tool_registration(self):
        @self.registry.tool(name="reverse_text", description="Reverses a string")
        def reverse_text(text: str) -> str:
            return text[::-1]

        resp = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "reverse_text",
                "arguments": {"text": "mcp-gateway"},
            },
        })
        self.assertEqual(resp["result"]["content"][0]["text"], "yawetag-pcm")

    async def test_mcp_to_openai_tools_format(self):
        openai_tools = self.registry.to_openai_tools()
        self.assertTrue(len(openai_tools) >= 2)
        calc_tool = next(t for t in openai_tools if t["function"]["name"] == "calculator")
        self.assertEqual(calc_tool["type"], "function")
        self.assertIn("parameters", calc_tool["function"])

    async def test_mcp_error_handling(self):
        # Unknown method
        resp = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 6,
            "method": "unknown_rpc_method",
        })
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

        # Unknown tool
        resp = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "non_existent_tool", "arguments": {}},
        })
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    async def test_mcp_batch_and_notifications(self):
        # 1. Batch execution
        batch_req = [
            {"jsonrpc": "2.0", "id": 10, "method": "ping"},
            {"jsonrpc": "2.0", "id": 11, "method": "tools/list"},
        ]
        batch_resp = await self.registry.handle_jsonrpc(batch_req)
        self.assertIsInstance(batch_resp, list)
        self.assertEqual(len(batch_resp), 2)
        self.assertEqual(batch_resp[0]["id"], 10)
        self.assertEqual(batch_resp[1]["id"], 11)

        # 2. Lifecycle notification produces no response object (returns None)
        notif_resp = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        self.assertIsNone(notif_resp)

        # 3. Standard resources/list and prompts/list
        res_list = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 12,
            "method": "resources/list",
        })
        self.assertEqual(res_list["result"], {"resources": [], "resourceTemplates": []})

        prompt_list = await self.registry.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 13,
            "method": "prompts/list",
        })
        self.assertEqual(prompt_list["result"], {"prompts": []})

    async def test_mcp_tool_extra_arguments_filtered(self):
        @self.registry.tool(name="strict_add", description="Add two numbers strictly")
        def strict_add(a: int, b: int) -> int:
            return a + b

        # Calling with hallucinated extra parameter 'explanation' does not crash
        res = await self.registry.call_tool(
            "strict_add",
            arguments={"a": 15, "b": 27, "explanation": "unrecognized parameter from LLM"},
        )
        self.assertFalse(res.is_error)
        self.assertIn("42", res.content[0]["text"])


class TestMCPHttpRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_mcp_health(self):
        res = self.client.get("/mcp/v1/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "healthy")

    def test_mcp_jsonrpc_post(self):
        res = self.client.post("/mcp", json={
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/list",
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], 100)
        self.assertIn("tools", data["result"])

    def test_mcp_http_batch_and_notification(self):
        # Batch over HTTP
        res = self.client.post("/mcp", json=[
            {"jsonrpc": "2.0", "id": 101, "method": "ping"},
            {"jsonrpc": "2.0", "id": 102, "method": "tools/list"},
        ])
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], 101)

        # Notification over HTTP returns 204 No Content
        notif_res = self.client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        self.assertEqual(notif_res.status_code, 204)

    def test_mcp_rest_tools_list_and_call(self):
        res = self.client.get("/mcp/v1/tools")
        self.assertEqual(res.status_code, 200)
        tools = res.json()["tools"]
        self.assertTrue(any(t["name"] == "calculator" for t in tools))

        call_res = self.client.post("/mcp/v1/call", json={
            "name": "calculator",
            "arguments": {"expression": "12 * 12"},
        })
        self.assertEqual(call_res.status_code, 200)
        self.assertIn("144", call_res.json()["content"][0]["text"])


class TestGatewayAdvancedFeatures(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_gateway_tracing_and_response_headers(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="chatcmpl-test-trace",
            provider="openai",
            model="gpt-4o",
            content="Hello from gateway",
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=120.5,
            retries=0,
            fallback_used=False,
        )

        headers = {
            "x-trace-id": "trace-custom-uuid-1234",
            "x-session-id": "session-test",
            "x-user-id": "user-test",
            "x-tags": "eval,bench,test",
        }
        res = self.client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Trace-Id"), "trace-custom-uuid-1234")
        self.assertEqual(res.headers.get("X-VeloRoute-Provider"), "openai")
        self.assertEqual(res.headers.get("X-VeloRoute-Model"), "gpt-4o")
        self.assertEqual(res.headers.get("X-Cache"), "MISS")
        self.assertEqual(res.headers.get("X-VeloRoute-Cached"), "false")

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_gateway_cache_control_bypass(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="chatcmpl-test-cache-bypass",
            provider="openai",
            model="gpt-4o",
            content="Direct uncached response",
            prompt_tokens=8,
            completion_tokens=4,
            latency_ms=95.0,
        )

        headers = {
            "Cache-Control": "no-cache",
        }
        res = self.client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "bypass cache test"}]},
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Cache"), "BYPASS")
        self.assertEqual(res.headers.get("X-VeloRoute-Cached"), "false")

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_gateway_cache_activation_cycle(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="chatcmpl-cached-val",
            provider="openai",
            model="gpt-4o",
            content="Cached answer content",
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=100.0,
        )

        headers = {"X-Cache": "true"}
        payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "cache test prompt 12345"}]}

        # First call is a MISS and stores into cache
        res1 = self.client.post("/v1/chat/completions", json=payload, headers=headers)
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.headers.get("X-Cache"), "MISS")

        # Second call hits the cache
        res2 = self.client.post("/v1/chat/completions", json=payload, headers=headers)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.headers.get("X-Cache"), "HIT")
        self.assertEqual(res2.headers.get("X-VeloRoute-Cached"), "true")
        self.assertIn("Cached answer content", res2.json()["choices"][0]["message"]["content"])

    def test_streaming_ttft_tracking(self):
        aggregator = StreamChunkAggregator()
        self.assertIsNone(aggregator.ttft_ms)

        aggregator.add_chunk("First token chunk")
        self.assertIsNotNone(aggregator.ttft_ms)
        self.assertGreaterEqual(aggregator.ttft_ms, 0.0)

        # Subsequent chunks do not reset ttft_ms
        initial_ttft = aggregator.ttft_ms
        aggregator.add_chunk("Second chunk")
        self.assertEqual(aggregator.ttft_ms, initial_ttft)

        event = StreamEvent(type="chunk", content="token", ttft_ms=aggregator.ttft_ms)
        self.assertEqual(event.ttft_ms, initial_ttft)


class TestModelCatalogUpdates(unittest.TestCase):
    def test_2025_2026_model_pricing_catalog(self):
        flagship_models = [
            "gpt-4.5",
            "gpt-4.5-preview",
            "o3",
            "o4-mini",
            "claude-3-7-sonnet-thinking",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "deepseek-r1-distill-llama-70b",
            "deepseek-r1-distill-qwen-32b",
            "codestral-2501",
            "mistral-large-2411",
            "qwen-2.5-coder-7b",
            "phi-4",
        ]
        for model in flagship_models:
            self.assertIn(
                model,
                DEFAULT_PRICING,
                f"Model '{model}' missing from DEFAULT_PRICING catalog",
            )
            pricing_entry = DEFAULT_PRICING[model]
            self.assertGreater(pricing_entry["input"], 0.0)
            self.assertGreater(pricing_entry["output"], 0.0)

    def test_2025_2026_model_context_windows(self):
        models = [
            ("gpt-4.5", 128_000),
            ("o3", 200_000),
            ("gemini-2.5-pro", 1_000_000),
            ("gemini-2.5-flash", 1_000_000),
            ("claude-3-7-sonnet-thinking", 200_000),
            ("phi-4", 16_000),
        ]
        for model, min_window in models:
            self.assertIn(
                model,
                DEFAULT_CONTEXT_WINDOWS,
                f"Model '{model}' missing from DEFAULT_CONTEXT_WINDOWS",
            )
            self.assertGreaterEqual(DEFAULT_CONTEXT_WINDOWS[model], min_window)


if __name__ == "__main__":
    unittest.main()
