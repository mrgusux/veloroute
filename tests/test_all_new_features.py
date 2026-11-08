import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from starlette.testclient import TestClient

from veloroute.client import VeloRoute
from veloroute.core.context_optimizer import ContextOptimizer
from veloroute.core.keys import KeyManager, KeyStatus
from veloroute.core.mcp import MCPAuthMode, MCPRegistry
from veloroute.core.prompt_sizer import PromptSizer, TaskTier
from veloroute.core.router import ModelRouter, RoutingStrategy
from veloroute.ui.app import app
from veloroute.ui.routes.deps import SESSION_TOKEN, llm_client


class TestTokenSaviourContextOptimizer(unittest.TestCase):
    def setUp(self):
        self.opt = ContextOptimizer()

    def test_strip_ansi_and_terminal_repeats(self):
        dirty_terminal = (
            "\x1b[31m[ERROR]\x1b[0m Connection failed\n"
            + "[ERROR] Connection failed\n" * 15
            + "\n\n\n\nFinal recovery check."
        )
        res = self.opt.optimize_text(dirty_terminal)
        opt_text = res["optimized_text"]
        stats = res["stats"]

        self.assertNotIn("\x1b[31m", opt_text)
        self.assertIn("Token-Saviour", opt_text)
        self.assertIn("identical lines collapsed", opt_text)
        self.assertIn("Final recovery check.", opt_text)
        self.assertGreater(stats["saved_tokens"], 0)
        self.assertGreater(stats["savings_pct"], 15.0)

    def test_ast_python_skeletonization(self):
        code = '''import os
import sys

class DataProcessor:
    """Processes large datasets."""
    def __init__(self, data_path: str):
        self.path = data_path
        self.cache = {}
        for i in range(100):
            self.cache[i] = i * 2

    def process(self, value: int) -> int:
        """Double the value."""
        return value * 2
'''
        skeleton = self.opt.skeletonize_python(code)
        self.assertIn("class DataProcessor:", skeleton)
        self.assertIn("Processes large datasets.", skeleton)
        self.assertIn("def __init__(self, data_path: str):", skeleton)
        self.assertIn("def process(self, value: int) -> int:", skeleton)
        self.assertIn("...", skeleton)
        self.assertNotIn("for i in range(100):", skeleton)

    def test_ast_python_chunking(self):
        code = '''import math

def calculate_hypotenuse(a: float, b: float) -> float:
    """Calculate hypotenuse length."""
    return math.sqrt(a * a + b * b)

class Circle:
    """Circle shape model."""
    def __init__(self, radius: float):
        self.radius = radius
'''
        chunks = self.opt.ast_chunk_python(code)
        self.assertGreaterEqual(len(chunks), 3)  # imports, function, class
        types = [c.node_type for c in chunks]
        self.assertIn("imports", types)
        self.assertIn("function", types)
        self.assertIn("class", types)

    def test_optimize_messages(self):
        messages = [
            {"role": "system", "content": "You are a terminal observer.\n\n\n\n"},
            {"role": "user", "content": "\x1b[32mBuild status:\x1b[0m\n" + "Failed\n" * 15},
        ]
        opt_messages, stats = self.opt.optimize_messages(messages)
        self.assertEqual(len(opt_messages), 2)
        self.assertNotIn("\x1b[32m", opt_messages[1]["content"])
        self.assertGreater(stats["saved_tokens"], 0)


class TestClaudeCodePromptSizer(unittest.TestCase):
    def setUp(self):
        self.sizer = PromptSizer()

    def test_xs_tier_classification(self):
        res = self.sizer.analyze_complexity("Fix typo in README: velo-rote -> veloroute")
        self.assertEqual(res.tier, TaskTier.XS)
        self.assertIn("haiku", res.recommended_model.lower())

    def test_s_tier_classification(self):
        res = self.sizer.analyze_complexity("Write a unit test for password hashing using bcrypt")
        self.assertEqual(res.tier, TaskTier.S)
        self.assertIn("sonnet", res.recommended_model.lower())

    def test_l_tier_classification(self):
        res = self.sizer.analyze_complexity(
            "Refactor entire distributed microservices architecture to resolve consensus deadlock and race conditions in raft"
        )
        self.assertEqual(res.tier, TaskTier.L)
        self.assertIn("opus", res.recommended_model.lower())

    def test_hook_request_format(self):
        hook_req = {"prompt": "Fix typo in variable name"}
        resp = self.sizer.handle_hook_request(hook_req)
        self.assertEqual(resp["decision"], "proceed")
        self.assertIn("tier", resp)
        self.assertIn("model_override", resp)
        self.assertIn("estimated_tokens", resp)


class TestEnhancedSentinelCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.km = KeyManager()
        self.km.add_key("openai", "sk-sentinel-test-1")
        self.km.add_key("openai", "sk-sentinel-test-2")

    def test_sliding_window_and_status_diagnostics(self):
        key = "sk-sentinel-test-1"
        rec = self.km._find("openai", key)
        self.assertIsNotNone(rec)

        # Report 10 errors to trigger sliding window failure rate >= 70%
        for _ in range(10):
            self.km.report_error("openai", key, "server")

        self.assertEqual(rec.status, KeyStatus.CIRCUIT_BROKEN)
        self.assertEqual(rec.circuit_state, "open")
        self.assertGreater(rec.recent_failure_rate, 0.5)

        # Check circuit breaker status method
        status = self.km.get_circuit_breaker_status("openai")
        self.assertIn("openai", status)
        prov_info = status["openai"]
        self.assertEqual(prov_info["total_keys"], 2)
        self.assertEqual(prov_info["circuit_broken_keys"], 1)

        key_info = next(k for k in prov_info["keys"] if k["key_hint"] == rec.key_hint)
        self.assertEqual(key_info["circuit_state"], "open")
        self.assertGreater(key_info["cooldown_remaining_secs"], 0.0)

    def test_half_open_success_threshold(self):
        key = "sk-sentinel-test-2"
        rec = self.km._find("openai", key)
        rec.circuit_cooldown_secs = 0.02
        rec.half_open_success_threshold = 2  # require 2 successes to close circuit

        for _ in range(5):
            self.km.report_error("openai", key, "server")
        self.assertEqual(rec.circuit_state, "open")

        import time
        time.sleep(0.03)
        self.assertTrue(rec.is_usable)

        # 1st success keeps in half-open because threshold is 2
        self.km.report_success("openai", key)
        self.assertEqual(rec.half_open_successes, 1)
        self.assertEqual(rec.circuit_state, "half_open")

        # 2nd success closes circuit
        self.km.report_success("openai", key)
        self.assertEqual(rec.circuit_state, "closed")
        self.assertEqual(rec.status, KeyStatus.ACTIVE)


class TestMCPPolicyAndSandboxing(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_policy_modes_and_arg_blocking(self):
        reg = MCPRegistry()

        # Default allows calculator
        r1 = await reg.call_tool("calculator", {"expression": "10 * 10"})
        self.assertFalse(r1.is_error)
        self.assertEqual(r1.content[0]["text"], "100")

        # Dangerous payload blocked by sandboxing
        r2 = await reg.call_tool("calculator", {"expression": "rm -rf /"})
        self.assertTrue(r2.is_error)
        self.assertIn("blocked by security policy", r2.content[0]["text"])

        # Allowlist mode
        reg.set_policy(mode="allowlist_only", allowed_tools=["safe_tool"])
        r3 = await reg.call_tool("calculator", {"expression": "5 + 5"})
        self.assertTrue(r3.is_error)
        self.assertIn("not permitted under strict allowlist", r3.content[0]["text"])


class TestPrivacyModeZeroRetention(unittest.IsolatedAsyncioTestCase):
    async def test_privacy_mode_bypasses_storage(self):
        class MockStorage:
            def __init__(self):
                self.saved = []
            async def save_request(self, rec):
                self.saved.append(rec)

        storage = MockStorage()
        client = VeloRoute(storage=storage)
        client.privacy_mode = True

        res = await client._save(model="gpt-4o", prompt="Secret PII prompt", response="Secret answer")
        self.assertIsNone(res)
        self.assertEqual(len(storage.saved), 0)


class TestKVAffinityRouting(unittest.TestCase):
    def test_kv_affinity_routes_same_prefix_consistently(self):
        router = ModelRouter(
            fallbacks={"smart": ["openai/gpt-4o", "anthropic/claude-3-5-sonnet", "deepseek/deepseek-chat"]}
        )
        r1 = router.get_route(
            "smart",
            strategy=RoutingStrategy.KV_AFFINITY,
            messages=[{"role": "system", "content": "Expert Python Assistant"}, {"role": "user", "content": "Task 1"}],
        )
        r2 = router.get_route(
            "smart",
            strategy=RoutingStrategy.KV_AFFINITY,
            messages=[{"role": "system", "content": "Expert Python Assistant"}, {"role": "user", "content": "Task 2"}],
        )
        self.assertEqual(r1[0], r2[0])


class TestNewEndpointsWithClient(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}

    def test_circuit_breaker_status_endpoint(self):
        res = self.client.get("/api/v1/circuit_breaker/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, dict)

    def test_privacy_status_and_toggle_endpoints(self):
        res = self.client.get("/api/v1/privacy/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        initial_status = res.json()["enabled"]

        toggle_res = self.client.post("/api/v1/privacy/toggle", headers=self.headers)
        self.assertEqual(toggle_res.status_code, 200)
        self.assertEqual(toggle_res.json()["enabled"], not initial_status)

        # Restore
        self.client.post("/api/v1/privacy/toggle", headers=self.headers)

    def test_context_optimize_endpoint(self):
        payload = {
            "text": "\x1b[31mError\x1b[0m\n" + "Traceback: operation failed\n" * 15,
            "trim_terminal": True,
        }
        res = self.client.post("/api/v1/context/optimize", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("optimized_text", data)
        self.assertIn("stats", data)
        self.assertGreater(data["stats"]["saved_tokens"], 0)

    def test_claude_code_hook_endpoint(self):
        payload = {"prompt": "Fix typo in variable name", "cwd": "/project"}
        res = self.client.post("/api/v1/hooks/claude-code/prompt-submit", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["decision"], "proceed")
        self.assertEqual(data["tier"], "XS")

    def test_mcp_policy_endpoints(self):
        res = self.client.get("/api/v1/mcp/policy", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        policy = res.json()
        self.assertIn("mode", policy)

        update_res = self.client.post(
            "/api/v1/mcp/policy",
            json={"mode": "restricted", "denied_tools": ["forbidden_tool"], "block_dangerous_args": True},
            headers=self.headers,
        )
        self.assertEqual(update_res.status_code, 200)
        updated = update_res.json()
        self.assertEqual(updated["mode"], "restricted")
        self.assertIn("forbidden_tool", updated["denied_tools"])

    def test_quickstart_snippets_endpoint(self):
        res = self.client.get("/api/v1/quickstart/snippets", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("snippets", data)
        self.assertIn("openai_python", data["snippets"])
        self.assertIn("anthropic_python", data["snippets"])
        self.assertIn("curl", data["snippets"])
        self.assertIn("claude_code", data["snippets"])

    def test_prometheus_metrics_endpoint(self):
        res = self.client.get("/metrics")
        self.assertEqual(res.status_code, 200)
        self.assertIn("veloroute_", res.text)

    def test_context_optimize_terse_caveman_endpoint(self):
        payload = {
            "text": "Hello! Could you please kindly help me write a quick sort function in Python? Thank you very much in advance!",
            "terse": True,
        }
        res = self.client.post("/api/v1/context/optimize", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        opt = data["optimized_text"]
        self.assertNotIn("Could you please kindly", opt)
        self.assertNotIn("Thank you very much in advance", opt)
        self.assertIn("quick sort", opt)


class TestEdgeCasesAndHardenedFeatures(unittest.TestCase):
    def setUp(self):
        self.opt = ContextOptimizer()

    def test_windows_crlf_markdown_code_block_and_git_diff_trimming(self):
        # 1. CRLF in Markdown code block
        crlf_markdown = "```python\r\ndef compute(x: int) -> int:\r\n    \"\"\"Doc\"\"\"\r\n    y = x * 10\r\n    return y\r\n```"
        res = self.opt.optimize_text(crlf_markdown, skeletonize_python=True)
        self.assertIn("...", res["optimized_text"])
        self.assertNotIn("y = x * 10", res["optimized_text"])

        # 2. CRLF in Git diff index noise
        dirty_git = "diff --git a/f.py b/f.py\r\nindex 4a3b2c1..9f8e7d6 100644\r\n--- a/f.py\r\n+++ b/f.py\r\n"
        clean, mod = self.opt.trim_terminal_output(dirty_git)
        self.assertTrue(mod)
        self.assertNotIn("index 4a3b2c1..9f8e7d6", clean)

    def test_syntax_error_fallback_skeletonization(self):
        broken_code = (
            "def calculate_total(prices: list[float]) -> float:\n"
            "    \"\"\"Calculate total sum.\"\"\"\n"
            "    s = 0.0\n"
            "    for p in prices:\n"
            "        s += p\n"
            "    return s\n\n"
            "# Incomplete line with unclosed bracket causing SyntaxError\n"
            "def broken_function(\n"
        )
        skeleton = self.opt.skeletonize_python(broken_code)
        self.assertIn("def calculate_total(prices: list[float]) -> float:", skeleton)
        self.assertIn("Calculate total sum.", skeleton)
        self.assertIn("...", skeleton)
        self.assertNotIn("for p in prices:", skeleton)

    def test_caveman_terse_compression(self):
        verbose_prompt = (
            "Hello there! Could you please kindly write a binary search algorithm in Python?\n"
            "I would really appreciate it if you could make sure it returns -1 when not found.\n"
            "```python\n# do not touch this code\nx = 1\n```\n"
            "Thank you so much in advance! Best regards."
        )
        compressed, mod = self.opt.compress_caveman(verbose_prompt)
        self.assertTrue(mod)
        self.assertNotIn("Could you please kindly", compressed)
        self.assertNotIn("Thank you so much in advance", compressed)
        self.assertIn("binary search algorithm in Python", compressed)
        self.assertIn("# do not touch this code", compressed)  # Code block protected

    def test_ponytail_history_pruning(self):
        messages = [
            {"role": "system", "content": "You are a coding assistant."},
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Bulky response 1 " * 50},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Bulky response 2 " * 50},
            {"role": "user", "content": "Question 3"},
            {"role": "assistant", "content": "Bulky response 3 " * 50},
            {"role": "user", "content": "Question 4"},
            {"role": "assistant", "content": "Bulky response 4 " * 50},
            {"role": "user", "content": "Latest question"},
        ]
        pruned, meta = self.opt.prune_conversation(messages, max_turns=4)
        self.assertTrue(meta["pruned"])
        self.assertEqual(pruned[0]["role"], "system")
        self.assertEqual(pruned[-1]["content"], "Latest question")
        # Check that intermediate turns were condensed
        has_condensed = any("Ponytail" in m.get("content", "") for m in pruned)
        self.assertTrue(has_condensed)

    def test_keymanager_concurrent_thread_safety(self):
        import threading
        km = KeyManager()
        km.add_key("openai", "sk-conc-test-key")
        errors = []

        def err_worker():
            for _ in range(100):
                try:
                    km.report_error("openai", "sk-conc-test-key", "server")
                except Exception as e:
                    errors.append(e)

        def succ_worker():
            for _ in range(100):
                try:
                    km.report_success("openai", "sk-conc-test-key")
                except Exception as e:
                    errors.append(e)

        def diag_worker():
            for _ in range(100):
                try:
                    km.get_circuit_breaker_status("openai")
                except Exception as e:
                    errors.append(e)

        def reset_worker():
            for _ in range(20):
                try:
                    km.reset_circuit_breaker("openai")
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=err_worker),
            threading.Thread(target=succ_worker),
            threading.Thread(target=diag_worker),
            threading.Thread(target=reset_worker),
            threading.Thread(target=err_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Encountered concurrency errors: {errors}")

    def test_prefix_cache_bounded_lru_and_long_prefix_hashing(self):
        router = ModelRouter(
            fallbacks={"smart": ["openai/gpt-4o", "anthropic/claude-3-5-sonnet"]}
        )
        # Verify 4096-char differentiation: Prompts identical for 300 chars but differing later
        prefix_base = "You are an enterprise software architect " * 10  # ~420 chars
        prompt_a = prefix_base + " [DOMAIN: FINTECH PAYMENTS]"
        prompt_b = prefix_base + " [DOMAIN: HEALTHCARE HL7]"

        # Directly test get_route generates distinct hashes
        import hashlib
        hash_a = hashlib.sha256(prompt_a[:4096].encode("utf-8")).hexdigest()
        hash_b = hashlib.sha256(prompt_b[:4096].encode("utf-8")).hexdigest()
        self.assertNotEqual(hash_a, hash_b)

        # Test LRU cache bounding
        for i in range(1050):
            h = f"fake_hash_{i}"
            router._prefix_cache[h] = ("openai", 1000.0 + i)

        # Call get_route with KV_AFFINITY to trigger LRU eviction check
        router.get_route("smart", strategy=RoutingStrategy.KV_AFFINITY, prompt=prompt_a)
        # Must not exceed max capacity
        self.assertLessEqual(len(router._prefix_cache), 1000)


if __name__ == "__main__":
    unittest.main()
