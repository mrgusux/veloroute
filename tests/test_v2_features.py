import os
import sys
import time
import unittest
import asyncio
from pathlib import Path

# Ensure package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from veloroute.core.keys import KeyManager, KeyStatus
from veloroute.core.router import ModelRouter, RoutingStrategy
from veloroute.core.stream import RetryPolicy, SmartRetryState
from veloroute.client import VeloRoute
from veloroute.schema import EmbeddingRequest, EmbeddingResponse, EmbeddingData, EmbeddingUsage
from starlette.testclient import TestClient
from veloroute.ui.app import app
from veloroute.ui.routes.deps import SESSION_TOKEN, llm_client


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.km = KeyManager()
        self.km.add_key("openai", "sk-test-circuit-1")
        self.km.add_key("openai", "sk-test-circuit-2")

    def test_circuit_tripping_on_server_errors(self):
        key = "sk-test-circuit-1"
        rec = self.km._find("openai", key)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.status, KeyStatus.ACTIVE)
        self.assertEqual(rec.circuit_state, "closed")

        # Report 4 server errors (below failure_threshold of 5)
        for _ in range(4):
            self.km.report_error("openai", key, "server")
        
        self.assertEqual(rec.status, KeyStatus.ACTIVE)
        self.assertEqual(rec.consecutive_errors, 4)
        self.assertEqual(rec.circuit_trips, 0)

        # 5th error trips the circuit breaker
        self.km.report_error("openai", key, "server")
        self.assertEqual(rec.status, KeyStatus.CIRCUIT_BROKEN)
        self.assertEqual(rec.circuit_state, "open")
        self.assertEqual(rec.circuit_trips, 1)
        self.assertFalse(rec.is_usable)

        # Verify key_count reflects the circuit broken key
        counts = self.km.key_count("openai")
        self.assertEqual(counts["circuit_broken"], 1)
        self.assertEqual(counts["active"], 1)  # key-2 is still active

    def test_circuit_auto_recovery_and_half_open_probe(self):
        key = "sk-test-circuit-1"
        rec = self.km._find("openai", key)
        rec.circuit_cooldown_secs = 0.05  # short cooldown for testing

        # Trip the circuit
        for _ in range(5):
            self.km.report_error("openai", key, "server")
        self.assertEqual(rec.status, KeyStatus.CIRCUIT_BROKEN)
        self.assertFalse(rec.is_usable)

        # Wait for cooldown
        time.sleep(0.06)

        # Should now be in half-open state and allow probe
        self.assertTrue(rec.is_usable)
        self.assertEqual(rec.circuit_state, "half_open")

        # Successful probe recovers the key
        self.km.report_success("openai", key)
        self.assertEqual(rec.status, KeyStatus.ACTIVE)
        self.assertEqual(rec.circuit_state, "closed")
        self.assertEqual(rec.consecutive_errors, 0)
        self.assertGreaterEqual(rec.total_successes, 1)

    def test_manual_circuit_breaker_reset(self):
        key = "sk-test-circuit-1"
        for _ in range(5):
            self.km.report_error("openai", key, "server")
        rec = self.km._find("openai", key)
        self.assertEqual(rec.status, KeyStatus.CIRCUIT_BROKEN)

        reset_count = self.km.reset_circuit_breaker("openai")
        self.assertEqual(reset_count, 1)
        self.assertEqual(rec.status, KeyStatus.ACTIVE)
        self.assertEqual(rec.circuit_state, "closed")

    def test_probe_concurrency_protection_and_escalation(self):
        k1 = "sk-test-circuit-1"
        rec = self.km._find("openai", k1)
        rec.circuit_cooldown_secs = 0.05

        # 1. Trip the key
        for _ in range(5):
            self.km.report_error("openai", k1, "server")
        self.assertEqual(rec.circuit_state, "open")

        time.sleep(0.06)
        self.assertTrue(rec.is_usable)

        # First request gets key for probe
        selected = self.km.get_next_key("openai")
        self.assertEqual(selected, k1)
        self.assertTrue(rec.probe_in_flight)
        # While probe is in flight, key is not usable by other requests
        self.assertFalse(rec.is_usable)

        # 2. If probe fails, immediately re-trips with escalated cooldown
        self.km.report_error("openai", k1, "server")
        self.assertEqual(rec.status, KeyStatus.CIRCUIT_BROKEN)
        self.assertEqual(rec.circuit_state, "open")
        self.assertEqual(rec.circuit_trips, 2)
        self.assertFalse(rec.probe_in_flight)

    def test_provider_circuit_health_and_failover(self):
        self.assertTrue(self.km.is_provider_healthy("openai"))
        self.assertEqual(self.km.get_provider_circuit_state("openai"), "closed")

        # Trip all keys for openai
        for _ in range(5):
            self.km.report_error("openai", "sk-test-circuit-1", "server")
            self.km.report_error("openai", "sk-test-circuit-2", "server")

        self.assertFalse(self.km.is_provider_healthy("openai"))
        self.assertEqual(self.km.get_provider_circuit_state("openai"), "open")


class TestExponentialBackoff(unittest.TestCase):
    def test_exponential_backoff_calculation_without_jitter(self):
        policy = RetryPolicy(
            max_retries=3,
            retry_delay=1.0,
            backoff_factor=2.0,
            max_delay=10.0,
            jitter=False
        )
        self.assertEqual(policy.calculate_delay(0), 1.0)
        self.assertEqual(policy.calculate_delay(1), 2.0)
        self.assertEqual(policy.calculate_delay(2), 4.0)
        self.assertEqual(policy.calculate_delay(3), 8.0)
        self.assertEqual(policy.calculate_delay(4), 10.0)  # capped at max_delay

    def test_exponential_backoff_with_jitter(self):
        policy = RetryPolicy(
            max_retries=3,
            retry_delay=2.0,
            backoff_factor=2.0,
            max_delay=30.0,
            jitter=True
        )
        delays = [policy.calculate_delay(1) for _ in range(20)]
        # All delays should be bounded between 0.5 * 4.0 (2.0) and 1.5 * 4.0 (6.0)
        self.assertTrue(all(2.0 <= d <= 6.0 for d in delays))
        # Delays should have jitter variation
        self.assertGreater(len(set(delays)), 1)


class TestIntelligentLoadBalancing(unittest.TestCase):
    def setUp(self):
        self.km = KeyManager()
        self.km.add_key("openai", "sk-oa-1")
        self.km.add_key("openai", "sk-oa-2")
        self.km.add_key("anthropic", "sk-ant-1")

    def test_least_used_key_selection(self):
        # Simulate traffic: key 1 gets 10 requests, key 2 gets 2 requests
        r1 = self.km._find("openai", "sk-oa-1")
        r2 = self.km._find("openai", "sk-oa-2")
        r1.total_requests = 10
        r2.total_requests = 2

        # In least_used strategy, key 2 must be picked
        chosen = self.km.get_next_key("openai", strategy="least_used")
        self.assertEqual(chosen, "sk-oa-2")
        self.assertEqual(r2.total_requests, 3)

    def test_least_busy_provider_routing(self):
        router = ModelRouter(
            fallbacks={"default-chain": ["openai", "anthropic"]},
            strategy=RoutingStrategy.LEAST_BUSY,
            key_manager=self.km
        )
        # Give openai 50 total requests, anthropic 5
        r_oa = self.km._find("openai", "sk-oa-1")
        r_oa.total_requests = 50
        r_ant = self.km._find("anthropic", "sk-ant-1")
        r_ant.total_requests = 5

        route = router.get_route("default-chain")
        # Least busy (anthropic with 5 requests) must be first
        self.assertEqual(route[0][0], "anthropic")
        self.assertEqual(route[1][0], "openai")


class TestUniversalModelAliasing(unittest.TestCase):
    def setUp(self):
        self.router = ModelRouter()
        self.client = VeloRoute()

    def test_alias_registration_and_resolution(self):
        self.client.alias("smart", "openai/gpt-4o")
        self.client.alias("fast", "groq/llama-3.3-70b")
        self.client.alias("super-fast", "fast")  # alias chaining

        self.assertEqual(self.client._resolve_model("smart"), "openai/gpt-4o")
        self.assertEqual(self.client._resolve_model("fast"), "groq/llama-3.3-70b")
        self.assertEqual(self.client._resolve_model("super-fast"), "groq/llama-3.3-70b")

        # Routing via alias
        route = self.client.router.get_route("smart")
        self.assertEqual(route[0], ("openai", "gpt-4o"))

        # Removing alias
        self.assertTrue(self.client.remove_alias("smart"))
        self.assertEqual(self.client._resolve_model("smart"), "smart")


class TestEmbeddingsAndAudio(unittest.IsolatedAsyncioTestCase):
    async def test_embed_mock_routing(self):
        client = VeloRoute()
        client.add_provider("mockemb", ["sk-mock-key"], base_url="https://api.mockemb.com/v1")
        
        # Verify EmbeddingRequest serialization
        req = EmbeddingRequest(model="text-embedding-3-small", input=["hello world", "foo bar"])
        payload = req.to_api_dict()
        self.assertEqual(payload["model"], "text-embedding-3-small")
        self.assertEqual(len(payload["input"]), 2)

        # Verify EmbeddingResponse model creation
        resp = EmbeddingResponse(
            model="text-embedding-3-small",
            data=[
                EmbeddingData(index=0, embedding=[0.1, 0.2, 0.3]),
                EmbeddingData(index=1, embedding=[0.4, 0.5, 0.6])
            ],
            usage=EmbeddingUsage(prompt_tokens=8, total_tokens=8),
            provider="mockemb"
        )
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.usage.total_tokens, 8)
        self.assertEqual(resp.provider, "mockemb")

    async def test_embedding_request_with_int_tokens(self):
        # OpenAI embeddings supports list of int tokens and list of lists of int tokens
        req1 = EmbeddingRequest(model="text-embedding-3-small", input=[101, 202, 303])
        self.assertEqual(req1.to_api_dict()["input"], [101, 202, 303])

        req2 = EmbeddingRequest(model="text-embedding-3-small", input=[[101, 202], [303, 404]])
        self.assertEqual(len(req2.to_api_dict()["input"]), 2)

    async def test_bare_model_embedding_and_audio_routing(self):
        client = VeloRoute()
        client.add_provider("openai", ["sk-mock-key"], base_url="https://api.openai.com/v1")
        
        # Test routing for bare models
        route_emb = client.router.get_route("text-embedding-3-small")
        self.assertEqual(route_emb[0], ("openai", "text-embedding-3-small"))

        route_whisper = client.router.get_route("whisper-1")
        self.assertEqual(route_whisper[0], ("openai", "whisper-1"))

        route_tts = client.router.get_route("tts-1")
        self.assertEqual(route_tts[0], ("openai", "tts-1"))


class TestProxyAndDashboardAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        llm_client.alias("smart-alias", "openai/gpt-4o")

    def test_v1_models_includes_aliases_and_groups(self):
        res = self.client.get("/v1/models")
        self.assertEqual(res.status_code, 200)
        data = res.json().get("data", [])
        ids = [m["id"] for m in data]
        self.assertIn("smart-alias", ids)
        virtual_model = next(m for m in data if m["id"] == "smart-alias")
        self.assertEqual(virtual_model["owned_by"], "virtual")

    def test_key_analytics_endpoint(self):
        res = self.client.get("/api/v1/analytics/keys", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_keys", data)
        self.assertIn("keys", data)

    def test_circuit_breaker_reset_endpoint(self):
        res = self.client.post("/api/v1/circuit_breaker/reset", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_router_aliases_crud_endpoint(self):
        # 1. Create alias
        create_res = self.client.post("/api/v1/router/aliases", json={
            "name": "cheap-model",
            "target": "deepseek/deepseek-chat"
        }, headers=self.headers)
        self.assertEqual(create_res.status_code, 200)

        # 2. List aliases
        list_res = self.client.get("/api/v1/router/aliases", headers=self.headers)
        self.assertEqual(list_res.status_code, 200)
        aliases = list_res.json()["aliases"]
        self.assertIn("cheap-model", aliases)
        self.assertEqual(aliases["cheap-model"], "deepseek/deepseek-chat")

        # 3. Delete alias
        del_res = self.client.delete("/api/v1/router/aliases/cheap-model", headers=self.headers)
        self.assertEqual(del_res.status_code, 200)

        # 4. Verify deleted
        list_res2 = self.client.get("/api/v1/router/aliases", headers=self.headers)
        self.assertNotIn("cheap-model", list_res2.json()["aliases"])

    def test_dashboard_endpoint_contains_tripped_keys(self):
        res = self.client.get("/api/v1/dashboard", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_tripped_keys", data)
        self.assertIn("aliases", data)


class TestInferredRoutingAndWeighted(unittest.TestCase):
    def test_bare_model_inferred_routing(self):
        client = VeloRoute()
        client.add_provider("openai", ["sk-oa"])
        client.add_provider("anthropic", ["sk-ant"])
        
        self.assertEqual(client.router.get_route("gpt-4o")[0], ("openai", "gpt-4o"))
        self.assertEqual(client.router.get_route("claude-3-5-sonnet")[0], ("anthropic", "claude-3-5-sonnet"))

    def test_weighted_routing_with_provider_path(self):
        router = ModelRouter(
            fallbacks={"openai": {"groq": 0.8, "together": 0.2}},
            strategy=RoutingStrategy.WEIGHTED
        )
        route = router.get_route("openai/gpt-4o")
        providers = [r[0] for r in route]
        self.assertIn("groq", providers)
        self.assertIn("together", providers)

    def test_circuit_broken_provider_pushed_to_tail(self):
        km = KeyManager()
        km.add_key("openai", "sk-oa-bad")
        km.add_key("anthropic", "sk-ant-good")
        router = ModelRouter(
            fallbacks={"multi": ["openai", "anthropic"]},
            strategy=RoutingStrategy.PRIORITY,
            key_manager=km
        )

        # Before failure: openai is first in priority
        route1 = router.get_route("multi")
        self.assertEqual(route1[0][0], "openai")

        # Trip openai keys
        for _ in range(5):
            km.report_error("openai", "sk-oa-bad", "server")

        # After failure: anthropic is promoted ahead of circuit-broken openai
        route2 = router.get_route("multi")
        self.assertEqual(route2[0][0], "anthropic")


if __name__ == "__main__":
    unittest.main()
