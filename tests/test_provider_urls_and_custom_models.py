import json
import unittest
from unittest.mock import AsyncMock, patch
from starlette.testclient import TestClient

from veloroute.ui.app import app
from veloroute.ui.routes.deps import SESSION_TOKEN, llm_client
from veloroute.schema import CompletionResponse
from veloroute.utils import is_free_model


class TestProviderUrlsAndCustomModels(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.auth_headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        # Register a mock provider for testing
        llm_client.add_provider("testprov", ["sk-testprov-key1"], "https://api.testprov.com/v1")

    def tearDown(self):
        llm_client.remove_provider("testprov")

    def test_is_free_model_classification(self):
        # 1. Obvious name indicators
        self.assertTrue(is_free_model("meta-llama/llama-3.2-3b-instruct:free"))
        self.assertTrue(is_free_model("google/gemini-2.0-flash-exp:free"))
        self.assertTrue(is_free_model("free/deepseek-chat"))
        self.assertTrue(is_free_model("deepseek-chat-free"))
        self.assertTrue(is_free_model("free-model-v1"))
        self.assertTrue(is_free_model("llama-3.1-8b (free)"))

        # 2. Local provider indicators
        self.assertTrue(is_free_model("llama3:latest", provider_name="ollama"))
        self.assertTrue(is_free_model("qwen-7b", base_url="http://localhost:11434/v1"))
        self.assertTrue(is_free_model("custom-local", base_url="http://127.0.0.1:8000/v1"))

        # 3. Upstream pricing metadata (zero vs non-zero)
        self.assertTrue(
            is_free_model(
                "qwen-2.5-coder",
                raw_info={"pricing": {"prompt": "0", "completion": "0"}},
            )
        )
        self.assertFalse(
            is_free_model(
                "gpt-4o",
                raw_info={"pricing": {"prompt": "0.0025", "completion": "0.01"}},
            )
        )

        # 4. Standard paid models
        self.assertFalse(is_free_model("gpt-4o", provider_name="openai"))
        self.assertFalse(is_free_model("claude-3-5-sonnet", provider_name="anthropic"))
        self.assertFalse(is_free_model("deepseek-chat", provider_name="deepseek"))

    def test_custom_models_management_on_client(self):
        prov = "testprov"
        self.assertIsNone(llm_client.get_custom_models(prov))

        # Set custom models
        llm_client.set_custom_models(prov, ["custom-model-a", "custom-model-b", "custom-model-a"])
        models = llm_client.get_custom_models(prov)
        self.assertEqual(models, ["custom-model-a", "custom-model-b"])

        # get_models returns custom models
        async def check_models():
            return await llm_client.get_models(prov)

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(check_models())
            self.assertEqual(res, ["custom-model-a", "custom-model-b"])
        finally:
            loop.close()

        # Remove custom models
        self.assertTrue(llm_client.remove_custom_models(prov))
        self.assertIsNone(llm_client.get_custom_models(prov))

    def test_provider_root_and_404(self):
        # 1. Existing provider root probe
        res = self.client.get("/p/testprov/v1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")
        self.assertEqual(res.json()["provider"], "testprov")

        # 2. Non-existent provider
        res404 = self.client.get("/p/nonexistentprov_xyz/v1")
        self.assertEqual(res404.status_code, 404)

        res_models_404 = self.client.get("/p/nonexistentprov_xyz/v1/models")
        self.assertEqual(res_models_404.status_code, 404)

    def test_provider_models_endpoint(self):
        # Set custom models on testprov
        llm_client.set_custom_models("testprov", ["m-alpha", "m-beta"])

        # GET /p/testprov/v1/models
        res = self.client.get("/p/testprov/v1/models")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["object"], "list")
        ids = [item["id"] for item in data["data"]]
        self.assertEqual(ids, ["m-alpha", "m-beta"])
        self.assertEqual(data["data"][0]["owned_by"], "testprov")

        # GET /p/testprov/models (without /v1)
        res_no_v1 = self.client.get("/p/testprov/models")
        self.assertEqual(res_no_v1.status_code, 200)
        self.assertEqual(len(res_no_v1.json()["data"]), 2)

        # GET /p/testprov/v1/models/{model_id}
        res_single = self.client.get("/p/testprov/v1/models/m-alpha")
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(res_single.json()["id"], "m-alpha")
        self.assertEqual(res_single.json()["owned_by"], "testprov")

        # Clear custom models
        llm_client.remove_custom_models("testprov")

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_provider_chat_completions(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="chatcmpl-test-123",
            provider="testprov",
            content="Hello from testprov!",
            model="m-alpha",
            prompt_tokens=10,
            completion_tokens=5,
        )

        # 1. Bare model name routed to /p/testprov/v1/chat/completions
        payload = {
            "model": "m-alpha",
            "messages": [{"role": "user", "content": "ping"}],
        }
        res = self.client.post("/p/testprov/v1/chat/completions", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["choices"][0]["message"]["content"], "Hello from testprov!")
        self.assertEqual(data["model"], "m-alpha")

        # Verify llm_client.complete was called with normalized 'testprov/m-alpha'
        mock_complete.assert_called_once()
        self.assertEqual(mock_complete.call_args.kwargs["model"], "testprov/m-alpha")

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_provider_legacy_completions(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="cmpl-test-456",
            provider="testprov",
            content="Generated text response",
            model="m-legacy",
            prompt_tokens=8,
            completion_tokens=4,
        )

        payload = {
            "model": "m-legacy",
            "prompt": "Say hello",
        }
        res = self.client.post("/p/testprov/v1/completions", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["object"], "text_completion")
        self.assertEqual(data["choices"][0]["text"], "Generated text response")
        self.assertEqual(data["model"], "m-legacy")

    @patch.object(llm_client, "embed", new_callable=AsyncMock)
    def test_provider_embeddings(self, mock_embed):
        from veloroute.schema import EmbeddingResponse, EmbeddingData, EmbeddingUsage
        mock_embed.return_value = EmbeddingResponse(
            model="text-embed",
            data=[EmbeddingData(embedding=[0.1, 0.2, 0.3], index=0)],
            usage=EmbeddingUsage(prompt_tokens=4, total_tokens=4),
        )

        payload = {
            "model": "text-embed",
            "input": "test text",
        }
        res = self.client.post("/p/testprov/v1/embeddings", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["object"], "list")
        mock_embed.assert_called_once()
        self.assertEqual(mock_embed.call_args.kwargs["model"], "testprov/text-embed")

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_provider_anthropic_messages(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="msg-test-789",
            provider="testprov",
            content="Anthropic style reply",
            model="claude-compat",
            prompt_tokens=12,
            completion_tokens=6,
        )

        payload = {
            "model": "claude-compat",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 100,
        }
        res = self.client.post("/p/testprov/v1/messages", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["type"], "message")
        self.assertEqual(data["content"][0]["text"], "Anthropic style reply")

    def test_sync_models_and_custom_models_api(self):
        # 1. Custom models endpoint GET (initially None)
        res_get = self.client.get("/api/v1/providers/testprov/custom_models", headers=self.auth_headers)
        self.assertEqual(res_get.status_code, 200)
        self.assertFalse(res_get.json()["is_configured"])

        # 2. Custom models endpoint PUT
        res_put = self.client.put(
            "/api/v1/providers/testprov/custom_models",
            json={"models": ["custom-x", "custom-y"]},
            headers=self.auth_headers,
        )
        self.assertEqual(res_put.status_code, 200)
        self.assertEqual(res_put.json()["custom_models"], ["custom-x", "custom-y"])
        self.assertEqual(llm_client.get_custom_models("testprov"), ["custom-x", "custom-y"])

        # 3. Models endpoint reflects custom models
        res_models = self.client.get("/api/v1/providers/testprov/models", headers=self.auth_headers)
        self.assertEqual(res_models.status_code, 200)
        self.assertTrue(res_models.json()["is_custom"])
        self.assertEqual(res_models.json()["models"], ["custom-x", "custom-y"])

        # 4. Sync models endpoint with mock discovery
        mock_discovered = [
            {"id": "model-free-1:free", "is_free": True, "raw": {}},
            {"id": "model-free-2", "is_free": True, "raw": {"pricing": {"prompt": "0", "completion": "0"}}},
            {"id": "model-paid-1", "is_free": False, "raw": {"pricing": {"prompt": "0.01", "completion": "0.02"}}},
        ]
        with patch.object(llm_client, "discover_models", new_callable=AsyncMock) as mock_disc:
            mock_disc.return_value = mock_discovered

            # Filter free
            res_sync_free = self.client.post(
                "/api/v1/providers/sync_models",
                json={"provider": "testprov", "filter": "free"},
                headers=self.auth_headers,
            )
            self.assertEqual(res_sync_free.status_code, 200)
            data_free = res_sync_free.json()
            self.assertEqual(data_free["count"], 2)
            self.assertEqual(data_free["models"], ["model-free-1:free", "model-free-2"])

            # Filter paid
            res_sync_paid = self.client.post(
                "/api/v1/providers/sync_models",
                json={"provider": "testprov", "filter": "paid"},
                headers=self.auth_headers,
            )
            self.assertEqual(res_sync_paid.status_code, 200)
            data_paid = res_sync_paid.json()
            self.assertEqual(data_paid["count"], 1)
            self.assertEqual(data_paid["models"], ["model-paid-1"])

            # Filter all + save
            res_sync_all = self.client.post(
                "/api/v1/providers/sync_models",
                json={"provider": "testprov", "filter": "all", "save": True},
                headers=self.auth_headers,
            )
            self.assertEqual(res_sync_all.status_code, 200)
            self.assertEqual(res_sync_all.json()["count"], 3)
            self.assertEqual(len(llm_client.get_custom_models("testprov")), 3)

        # 5. Delete custom models (clears custom list, restores dynamic)
        res_del = self.client.delete("/api/v1/providers/testprov/custom_models", headers=self.auth_headers)
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(llm_client.get_custom_models("testprov"))

    def test_is_free_model_numeric_pricing_and_flags(self):
        # Numeric 0 and 0.0 (previously failed due to falsy 0 bug)
        self.assertTrue(is_free_model("num-zero-int", raw_info={"pricing": {"prompt": 0, "completion": 0}}))
        self.assertTrue(is_free_model("num-zero-float", raw_info={"pricing": {"prompt": 0.0, "completion": 0.0}}))
        self.assertTrue(is_free_model("embed-free", raw_info={"pricing": {"prompt": 0.0}}))
        # Explicit boolean flag
        self.assertTrue(is_free_model("flag-free", raw_info={"is_free": True}))
        self.assertTrue(is_free_model("flag-free-2", raw_info={"free": True}))
        # Paid model with numeric pricing
        self.assertFalse(is_free_model("paid-model", raw_info={"pricing": {"prompt": 0.001, "completion": 0.002}}))

    def test_custom_models_strips_self_prefix(self):
        llm_client.set_custom_models("testprov", ["testprov/alpha", "beta", "  testprov/gamma  "])
        models = llm_client.get_custom_models("testprov")
        self.assertEqual(models, ["alpha", "beta", "gamma"])
        llm_client.remove_custom_models("testprov")

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_mismatched_provider_prefix_handling(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="chatcmpl-test-456",
            provider="testprov",
            content="Handled mismatched prefix",
            model="target-model",
            prompt_tokens=10,
            completion_tokens=5,
        )
        # Register a second provider
        llm_client.add_provider("otherprov", ["sk-other"], "https://api.other.com/v1")
        try:
            # Client accidentally sends 'otherprov/target-model' to '/p/testprov/v1/chat/completions'
            payload = {
                "model": "otherprov/target-model",
                "messages": [{"role": "user", "content": "hello"}],
            }
            res = self.client.post("/p/testprov/v1/chat/completions", json=payload)
            self.assertEqual(res.status_code, 200)
            # Upstream was called with 'testprov/target-model', stripping the other provider prefix
            self.assertEqual(mock_complete.call_args.kwargs["model"], "testprov/target-model")
            # Client response returns the requested model
            self.assertEqual(res.json()["model"], "otherprov/target-model")
        finally:
            llm_client.remove_provider("otherprov")

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_anthropic_messages_model_preservation(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="msg-test-clean",
            provider="testprov",
            content="Anthropic clean model reply",
            model="testprov/claude-compat",
            prompt_tokens=15,
            completion_tokens=8,
        )
        payload = {
            "model": "claude-compat",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 100,
        }
        res = self.client.post("/p/testprov/v1/messages", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["model"], "claude-compat")

    def test_provider_chat_completions_streaming_returns_display_model(self):
        async def mock_stream(*args, **kwargs):
            yield "Hello"
            yield " world"

        with patch.object(llm_client, "stream", side_effect=mock_stream):
            payload = {
                "model": "m-alpha",
                "messages": [{"role": "user", "content": "stream test"}],
                "stream": True,
            }
            res = self.client.post("/p/testprov/v1/chat/completions", json=payload)
            self.assertEqual(res.status_code, 200)
            lines = [l for l in res.text.split("\n") if l.startswith("data: ") and not l.startswith("data: [DONE]")]
            self.assertTrue(len(lines) > 0)
            chunk_data = json.loads(lines[0][6:])
            self.assertEqual(chunk_data["model"], "m-alpha")

    def test_virtual_key_with_bare_and_prefixed_model(self):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            vk, secret = loop.run_until_complete(
                llm_client.virtual_keys.create_key("test-key", allowed_models=["m-alpha"])
            )
            # Authorization with bare model
            auth1 = loop.run_until_complete(
                llm_client.virtual_keys.authorize(secret, model="m-alpha")
            )
            self.assertIsNotNone(auth1)

            # Authorization with prefixed model 'testprov/m-alpha' must also succeed!
            auth2 = loop.run_until_complete(
                llm_client.virtual_keys.authorize(secret, model="testprov/m-alpha")
            )
            self.assertIsNotNone(auth2)

            loop.run_until_complete(llm_client.virtual_keys.delete_key(vk.id))
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
