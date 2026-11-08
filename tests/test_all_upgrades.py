import os
import sys
import unittest
import asyncio
from pathlib import Path

# Ensure package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from veloroute.core.keys import KeyManager, KeyStatus
from veloroute.core.router import ModelRouter, RoutingStrategy
from veloroute.client import VeloRoute
from veloroute.storage import StorageManager, StorageBackend
from veloroute.utils import parse_model, MODEL_PRICING, CONTEXT_WINDOWS
from veloroute.providers.registry import PROVIDER_REGISTRY
from veloroute.core.semantic import SemanticRouter
from veloroute.core.guardrail import GuardrailManager
from veloroute.schema import CompletionRequest, Message
from veloroute.core.rate_limit import RateLimitManager
from veloroute.core.config_loader import EnvConfigLoader
from veloroute.core.cache import SQLCache
from veloroute.core.injection import InjectionGuard
from veloroute.core.semantic_cache import SemanticCache
from veloroute.core.groups import GroupManager
from veloroute.storage.backends.sql import SQLStorage


class TestKeyManager(unittest.TestCase):
    def setUp(self):
        self.km = KeyManager()

    def test_add_and_rotate_keys(self):
        self.km.add_key("openai", "sk-test11111111111111111111111111111111")
        self.km.add_key("openai", "sk-test22222222222222222222222222222222")
        k1 = self.km.get_key("openai")
        k2 = self.km.get_key("openai")
        self.assertNotEqual(k1, k2)
        counts = self.km.key_count("openai")
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["active"], 2)
        self.assertEqual(counts["rate_limited"], 0)

    def test_set_keys(self):
        self.km.add_key("testprov", "sk-oldkey-orig")
        self.km.set_keys("testprov", ["sk-key-alpha", "sk-key-bravo"])
        stats = self.km.get_stats("testprov")
        self.assertEqual(len(stats), 2)
        hints = [s["hint"] for s in stats]
        self.assertTrue(any("lpha" in h for h in hints))
        self.assertTrue(any("ravo" in h for h in hints))

    def test_remove_key_by_exact_and_hint(self):
        self.km.add_key("groq", "gsk_11111111111111111111111111111111")
        self.km.add_key("groq", "gsk_22222222222222222222222222222222")
        self.assertEqual(self.km.key_count("groq")["total"], 2)
        
        # Remove by exact key
        removed = self.km.remove_key("groq", "gsk_11111111111111111111111111111111")
        self.assertTrue(removed)
        self.assertEqual(self.km.key_count("groq")["total"], 1)

        # Remove remaining key by hint
        stats = self.km.get_stats("groq")
        hint = stats[0]["hint"]
        removed = self.km.remove_key("groq", hint)
        self.assertTrue(removed)
        self.assertEqual(self.km.key_count("groq")["total"], 0)

    def test_remove_provider(self):
        self.km.add_key("anthropic", "sk-ant-test")
        self.assertTrue(self.km.remove_provider("anthropic"))
        self.assertEqual(self.km.key_count("anthropic")["total"], 0)
        self.assertNotIn("anthropic", self.km.list_providers())

    def test_rate_limit_and_recovery(self):
        self.km.add_key("cohere", "key-cohere-1")
        self.km.report_error("cohere", "key-cohere-1", "rate_limit")
        stats = self.km.get_stats("cohere")
        self.assertEqual(stats[0]["status"], "rate_limited")
        counts = self.km.key_count("cohere")
        self.assertEqual(counts["rate_limited"], 1)
        self.assertEqual(counts["active"], 0)


class TestModelRouter(unittest.TestCase):
    def setUp(self):
        self.router = ModelRouter()

    def test_fallbacks_and_remove_provider(self):
        self.router.fallbacks = {
            "openai": ["groq", "gemini"],
            "openai/gpt-4o": ["anthropic/claude-3-5-sonnet"],
            "deepseek": ["openai"]
        }
        self.assertEqual(len(self.router.fallbacks.get("openai")), 2)
        
        # Remove provider groq
        self.router.remove_provider("groq")
        self.assertEqual(self.router.fallbacks.get("openai"), ["gemini"])

        # Remove provider openai
        self.router.remove_provider("openai")
        self.assertNotIn("openai", self.router.fallbacks)
        self.assertNotIn("openai/gpt-4o", self.router.fallbacks)
        self.assertEqual(self.router.fallbacks.get("deepseek"), [])

    def test_dynamic_groups(self):
        self.router.groups = {
            "fast-group": ["groq/llama-3.3-70b", "deepseek/deepseek-chat"]
        }
        route = self.router.get_route("fast-group")
        self.assertEqual(route[0], ("groq", "llama-3.3-70b"))
        self.assertEqual(route[1], ("deepseek", "deepseek-chat"))


class TestVeloRouteClient(unittest.TestCase):
    def test_provider_management(self):
        client = VeloRoute()
        client.add_provider("custom_ai", ["sk-key1", "sk-key2"], "https://custom.ai/v1")
        self.assertIn("custom_ai", client.get_providers())
        self.assertEqual(client._providers["custom_ai"].base_url, "https://custom.ai/v1")
        self.assertEqual(client.key_manager.key_count("custom_ai")["total"], 2)

        # Update provider
        client.update_provider("custom_ai", api_keys=["sk-new1"], base_url="https://new-custom.ai/v1")
        self.assertEqual(client._providers["custom_ai"].base_url, "https://new-custom.ai/v1")
        self.assertEqual(client.key_manager.key_count("custom_ai")["total"], 1)

        # Remove single key
        client.remove_key("custom_ai", "sk-new1")
        self.assertEqual(client.key_manager.key_count("custom_ai")["total"], 0)

        # Remove provider
        client.remove_provider("custom_ai")
        self.assertNotIn("custom_ai", client.get_providers())

    def test_modern_models_metadata(self):
        # Verify modern models are defined in pricing & context windows
        self.assertIn("o1", MODEL_PRICING)
        self.assertIn("claude-3-5-sonnet", MODEL_PRICING)
        self.assertIn("gemini-2.0-flash", MODEL_PRICING)
        self.assertIn("deepseek-v3", MODEL_PRICING)
        self.assertIn("deepseek-r1", MODEL_PRICING)
        self.assertIn("llama-3.3-70b", MODEL_PRICING)

        self.assertGreaterEqual(CONTEXT_WINDOWS.get("o1", 0), 128000)
        self.assertGreaterEqual(CONTEXT_WINDOWS.get("claude-3-5-sonnet", 0), 200000)
        self.assertGreaterEqual(CONTEXT_WINDOWS.get("gemini-2.0-flash", 0), 1000000)


class TestResilienceAndFixes(unittest.TestCase):
    def test_gemini_registry_endpoint(self):
        gemini_url = PROVIDER_REGISTRY.get("GEMINI")
        google_url = PROVIDER_REGISTRY.get("GOOGLE")
        self.assertTrue(gemini_url.endswith("/openai"))
        self.assertTrue(google_url.endswith("/openai"))

    def test_sql_storage_url_normalization(self):
        s1 = SQLStorage(url="sqlite:///test.db")
        self.assertTrue(s1.url.startswith("sqlite+aiosqlite:///"))
        s2 = SQLStorage(url="postgresql://user:pass@localhost/db")
        self.assertTrue(s2.url.startswith("postgresql+asyncpg://"))

    def test_semantic_router_edge_cases(self):
        router = SemanticRouter(
            rules={"math": [r"calc"]},
            routes={"math": "math-model"},
            default_intent="general"
        )
        # Empty and None prompts should return default intent
        self.assertEqual(router.classify(None), "general")
        self.assertEqual(router.classify(""), "general")
        self.assertEqual(router.classify("   "), "general")
        self.assertEqual(router.classify("calculate this"), "math")

    def test_guardrail_masking_idempotency(self):
        guard = GuardrailManager()
        masked = guard.mask_prompt("My secret is sk-proj-1234567890abcdef1234567890abcdef")
        # Masking again should not re-wrap the placeholder
        remasked = guard.mask_prompt(masked)
        self.assertEqual(masked, remasked)
        # Unmasking should restore the original secret
        unmasked = guard.unmask_response(remasked)
        self.assertEqual(unmasked, "My secret is sk-proj-1234567890abcdef1234567890abcdef")


class TestFastAPIRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from starlette.testclient import TestClient
        from veloroute.ui.app import app
        from veloroute.ui.routes.deps import SESSION_TOKEN
        cls.client = TestClient(app)
        cls.headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}

    def test_base_page(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("VeloRoute Dashboard", res.text)
        self.assertIn("providers-grid", res.text)

    def test_provider_and_key_crud(self):
        # 1. Add provider
        add_res = self.client.post("/api/v1/providers", json={
            "name": "testfastapi",
            "api_keys": ["sk-testapi-key1", "sk-testapi-key2"],
            "base_url": "https://api.testfastapi.com/v1"
        }, headers=self.headers)
        self.assertEqual(add_res.status_code, 200)

        # 2. List keys
        keys_res = self.client.get("/api/v1/providers/testfastapi/keys", headers=self.headers)
        self.assertEqual(keys_res.status_code, 200)
        stats = keys_res.json().get("stats", [])
        self.assertEqual(len(stats), 2)
        hint = stats[0]["hint"]

        # 3. Delete single key
        del_key_res = self.client.delete(f"/api/v1/providers/testfastapi/keys?key={hint}", headers=self.headers)
        self.assertEqual(del_key_res.status_code, 200)
        self.assertTrue(del_key_res.json()["removed"])

        # 4. Verify 1 key remains
        keys_res2 = self.client.get("/api/v1/providers/testfastapi/keys", headers=self.headers)
        self.assertEqual(len(keys_res2.json()["stats"]), 1)

        # 5. Update provider
        upd_res = self.client.put("/api/v1/providers/testfastapi", json={
            "base_url": "https://updated.testfastapi.com/v1",
            "api_keys": ["sk-brandnew-1"]
        }, headers=self.headers)
        self.assertEqual(upd_res.status_code, 200)

        # 6. Delete provider
        del_res = self.client.delete("/api/v1/providers/testfastapi", headers=self.headers)
        self.assertEqual(del_res.status_code, 200)

    def test_proxy_endpoints(self):
        # Set proxy
        p_res = self.client.post("/api/v1/proxy", json={"proxy": "http://127.0.0.1:8888"}, headers=self.headers)
        self.assertEqual(p_res.status_code, 200)
        self.assertEqual(p_res.json()["proxy"], "http://127.0.0.1:8888")

        # Get proxy
        g_res = self.client.get("/api/v1/proxy", headers=self.headers)
        self.assertEqual(g_res.status_code, 200)
        self.assertEqual(g_res.json()["proxy"], "http://127.0.0.1:8888")

        # Clear proxy
        d_res = self.client.delete("/api/v1/proxy", headers=self.headers)
        self.assertEqual(d_res.status_code, 200)
        self.assertIsNone(d_res.json()["proxy"])

    def test_router_endpoints(self):
        # Set strategy
        s_res = self.client.post("/api/v1/router/strategy", json={"strategy": "round_robin"}, headers=self.headers)
        self.assertEqual(s_res.status_code, 200)

        # Set fallbacks
        f_res = self.client.post("/api/v1/router/fallbacks", json={"fallbacks": {"testprimary": ["testfallback"]}}, headers=self.headers)
        self.assertEqual(f_res.status_code, 200)

        # Get router
        r_res = self.client.get("/api/v1/router", headers=self.headers)
        self.assertEqual(r_res.status_code, 200)
        self.assertEqual(r_res.json()["strategy"], "round_robin")
        self.assertIn("testprimary", r_res.json()["fallbacks"])


class TestCLISubprocess(unittest.TestCase):
    def test_cli_unicode_and_commands(self):
        import subprocess
        python_exe = sys.executable
        env = os.environ.copy()
        # Explicitly remove PYTHONUTF8 to simulate default Windows console
        env.pop("PYTHONUTF8", None)

        # 1. Help command with unicode characters
        p = subprocess.run([python_exe, "-m", "veloroute.cli", "help"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0)
        self.assertIn("Universal LLM Router", p.stdout)

        # 2. Providers add
        p = subprocess.run([python_exe, "-m", "veloroute.cli", "providers", "add", "clitest", "key-a,key-b", "--base-url", "https://api.clitest.com"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0)

        # 3. Providers edit
        p = subprocess.run([python_exe, "-m", "veloroute.cli", "providers", "edit", "clitest", "--base-url", "https://api.clitest2.com"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0)

        # 4. Keys remove single key
        p = subprocess.run([python_exe, "-m", "veloroute.cli", "keys", "remove", "clitest", "key-a"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0)

        # 5. Providers remove
        p = subprocess.run([python_exe, "-m", "veloroute.cli", "providers", "remove", "clitest"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0)

        # 6. Proxy set, show, clear
        p = subprocess.run([python_exe, "-m", "veloroute.cli", "proxy", "set", "http://127.0.0.1:9099"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0)

        p = subprocess.run([python_exe, "-m", "veloroute.cli", "proxy", "show"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0)
        self.assertIn("9099", p.stdout)

        p = subprocess.run([python_exe, "-m", "veloroute.cli", "proxy", "clear"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0)


class TestExtendedUpgradesAndEdgeCases(unittest.TestCase):
    def test_schema_message_serialization(self):
        msg = Message(role="user", content="Hello world")
        req = CompletionRequest(model="openai/gpt-4o", messages=[msg])
        d = req.to_api_dict()
        # Ensure null values are excluded from user messages
        self.assertEqual(len(d["messages"]), 1)
        self.assertEqual(d["messages"][0], {"role": "user", "content": "Hello world"})
        self.assertNotIn("tool_calls", d["messages"][0])
        self.assertNotIn("tool_call_id", d["messages"][0])
        self.assertNotIn("name", d["messages"][0])

    def test_rate_limit_default_fallback(self):
        mgr = RateLimitManager({"default": {"rpm": 100, "tpm": 50000}, "groq": {"rpm": 30}})
        # Test fallback to default
        l1 = mgr.get_limiter("openai/gpt-4o")
        self.assertIsNotNone(l1.rpm_bucket)
        self.assertEqual(l1.rpm_bucket.limit, 100)
        
        # Test provider-level override
        l2 = mgr.get_limiter("groq/llama-3.3-70b")
        self.assertIsNotNone(l2.rpm_bucket)
        self.assertEqual(l2.rpm_bucket.limit, 30)

    def test_env_config_loader_singular_and_base_url(self):
        os.environ["MISTRAL_API_KEY"] = "sk-mistral-test"
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434/v1"
        try:
            configs = EnvConfigLoader().load_configs()
            self.assertIn("MISTRAL", configs)
            self.assertEqual(configs["MISTRAL"]["api_keys"], "sk-mistral-test")
            self.assertIn("OLLAMA", configs)
            self.assertEqual(configs["OLLAMA"]["base_url"], "http://localhost:11434/v1")
        finally:
            os.environ.pop("MISTRAL_API_KEY", None)
            os.environ.pop("OLLAMA_BASE_URL", None)

    def test_sql_cache_url_normalization(self):
        c1 = SQLCache(url="sqlite:///test_cache.db")
        self.assertTrue(c1.url.startswith("sqlite+aiosqlite:///"))
        c2 = SQLCache(url="postgresql://user:pass@localhost/db")
        self.assertTrue(c2.url.startswith("postgresql+asyncpg://"))

    def test_injection_and_semantic_cache_none_inputs(self):
        ig = InjectionGuard()
        res = ig.scan(None)
        self.assertFalse(res.blocked)
        self.assertEqual(res.score, 0.0)

        sc = SemanticCache()
        self.assertIsNone(asyncio.run(sc.get(None)))
        self.assertIsNone(asyncio.run(sc.get("")))

    def test_router_empty_candidates_round_robin(self):
        router = ModelRouter()
        res = router._apply_strategy([], "empty-model", strategy=RoutingStrategy.ROUND_ROBIN)
        self.assertEqual(res, [])

    def test_group_manager_and_router_remove_provider(self):
        groups = GroupManager({"fast": ["groq/llama-3.3", "openai/gpt-4o"]})
        router = ModelRouter(groups=groups)
        self.assertIn("groq/llama-3.3", groups.get("fast"))
        router.remove_provider("groq")
        self.assertEqual(groups.get("fast"), ["openai/gpt-4o"])

    def test_storage_manager_string_backend(self):
        sm = StorageManager(backend="sqlite")
        self.assertEqual(sm.backend_type, StorageBackend.SQLITE)
        sm2 = StorageManager(backend="postgresql", url="postgresql+asyncpg://localhost/test")
        self.assertEqual(sm2.backend_type, StorageBackend.POSTGRES)


if __name__ == "__main__":
    unittest.main()
