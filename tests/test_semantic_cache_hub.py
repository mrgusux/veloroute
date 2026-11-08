import unittest
import asyncio
from starlette.testclient import TestClient

from veloroute.core.semantic_cache import SemanticCache
from veloroute.schema import CompletionResponse
from veloroute.ui.app import app
from veloroute.ui.routes.deps import SESSION_TOKEN, llm_client


class TestSemanticCacheHub(unittest.TestCase):
    def setUp(self):
        self.cache = SemanticCache(similarity_threshold=0.80, max_size=100, ttl=3600)
        self.client = TestClient(app)
        self.auth_headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}

    def _sample_response(self, text: str = "Paris is the capital of France."):
        return CompletionResponse(
            id="chatcmpl-test",
            created_at=12345678,
            model="mock/test-model",
            provider="mock",
            content=text,
            prompt_tokens=10,
            completion_tokens=8,
            latency_ms=120.0,
            cost_usd=0.0001,
        )

    def test_semantic_cache_core_operations(self):
        async def run():
            resp = self._sample_response("Paris is the capital of France.")
            await self.cache.set("What is the capital of France?", resp, model="mock/test-model")

            # 1. Exact match hit
            hit1 = await self.cache.get("What is the capital of France?", model="mock/test-model")
            self.assertIsNotNone(hit1)
            self.assertEqual(hit1.content, "Paris is the capital of France.")

            # 2. Semantic equivalent hit
            hit2 = await self.cache.get("Tell me the capital of France", model="mock/test-model")
            self.assertIsNotNone(hit2)
            self.assertEqual(hit2.content, "Paris is the capital of France.")

            # 3. Completely different query - should miss
            miss = await self.cache.get("How do I bake a chocolate cake?", model="mock/test-model")
            self.assertIsNone(miss)

            # 4. Check entries inspection
            entries = self.cache.entries()
            self.assertGreaterEqual(len(entries), 1)
            self.assertEqual(entries[0]["model"], "mock/test-model")
            self.assertIn("capital of France", entries[0]["prompt"])

            # 5. Check test_similarity without altering hits/misses
            stats_before = await self.cache.stats()
            sim = self.cache.test_similarity("What is France's capital city?", model="mock/test-model")
            self.assertTrue(sim["is_hit"])
            self.assertGreater(sim["best_score"], 0.8)
            stats_after = await self.cache.stats()
            self.assertEqual(stats_before["hits"], stats_after["hits"])
            self.assertEqual(stats_before["misses"], stats_after["misses"])

            # 6. Delete entry
            storage_key = entries[0]["key"]
            deleted = self.cache.delete_entry(storage_key)
            self.assertTrue(deleted)
            self.assertEqual(len(self.cache.entries()), 0)

            # 7. Update settings
            self.cache.update_settings(threshold=0.95, ttl=1800, max_size=200)
            self.assertEqual(self.cache.threshold, 0.95)
            self.assertEqual(self.cache.ttl, 1800.0)
            self.assertEqual(self.cache.max_size, 200)

            # 8. Clear cache
            await self.cache.set("Hello world", resp)
            cleared = await self.cache.clear()
            self.assertEqual(cleared, 1)

        asyncio.run(run())

    def test_cache_api_endpoints(self):
        # 1. Test unauthenticated request
        res = self.client.get("/api/v1/cache/stats")
        self.assertEqual(res.status_code, 401)

        # 2. Test authenticated stats
        res = self.client.get("/api/v1/cache/stats", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("stats", data)

        # 3. Test populate and entries endpoint
        llm_client._semantic_cache.update_settings(threshold=0.80)
        sample_resp = self._sample_response("Berlin is the capital of Germany.")
        asyncio.run(llm_client._semantic_cache.set("What is the capital of Germany?", sample_resp, model="mock/test"))

        res_entries = self.client.get("/api/v1/cache/entries?limit=10", headers=self.auth_headers)
        self.assertEqual(res_entries.status_code, 200)
        entries_data = res_entries.json()
        self.assertGreaterEqual(entries_data["count"], 1)

        # 4. Test similarity test endpoint
        res_test = self.client.post(
            "/api/v1/cache/test",
            headers=self.auth_headers,
            json={"prompt": "Tell me Germany's capital city", "model": "mock/test"},
        )
        self.assertEqual(res_test.status_code, 200)
        test_data = res_test.json()
        self.assertTrue(test_data["result"]["is_hit"])

        # 5. Test config update endpoint
        res_cfg = self.client.post(
            "/api/v1/cache/config",
            headers=self.auth_headers,
            json={"threshold": 0.90, "ttl": 7200, "max_size": 800},
        )
        self.assertEqual(res_cfg.status_code, 200)
        cfg_data = res_cfg.json()
        self.assertEqual(cfg_data["current_threshold"], 0.90)

        # 6. Test delete entry endpoint
        key_to_del = entries_data["entries"][0]["key"]
        res_del = self.client.request(
            "DELETE",
            "/api/v1/cache/entry",
            headers=self.auth_headers,
            json={"key": key_to_del},
        )
        self.assertEqual(res_del.status_code, 200)

        # 7. Test clear endpoint
        res_clr = self.client.post("/api/v1/cache/clear", headers=self.auth_headers)
        self.assertEqual(res_clr.status_code, 200)


if __name__ == "__main__":
    unittest.main()
