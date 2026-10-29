import asyncio
import hashlib
import hmac
import json
import unittest
from unittest.mock import AsyncMock, patch
from starlette.testclient import TestClient

from llmcycle.core.webhooks import WebhookDispatcher, WebhookEvent, get_webhook_dispatcher
from llmcycle.ui.app import app
from llmcycle.ui.routes.deps import SESSION_TOKEN, llm_client
from llmcycle.schema import CompletionResponse, StreamChunk


class TestWebhooksAndAnthropic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.auth_headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}

    def test_webhook_event_signature(self):
        dispatcher = WebhookDispatcher(url="https://example.com/webhook", secret="my_secret_key")
        payload = b'{"hello": "world"}'
        sig = dispatcher._sign(payload)
        expected = hmac.new(b"my_secret_key", payload, hashlib.sha256).hexdigest()
        self.assertEqual(sig, expected)

    async def test_webhook_dispatch_and_history(self):
        dispatcher = WebhookDispatcher(url="https://example.com/webhook", secret="secret123")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.is_success = True

            delivered = await dispatcher._deliver(
                WebhookEvent(event="circuit.tripped", data={"provider": "mock", "key": "k1"})
            )
            self.assertTrue(delivered)
            self.assertEqual(len(dispatcher.get_history()), 1)
            entry = dispatcher.get_history()[0]
            self.assertEqual(entry["event"], "circuit.tripped")
            self.assertEqual(entry["status"], "delivered")

    def test_webhooks_api_endpoints(self):
        # 1. Status
        res = self.client.get("/api/v1/webhooks/status", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("configured", res.json())

        # 2. History
        hist_res = self.client.get("/api/v1/webhooks/history", headers=self.auth_headers)
        self.assertEqual(hist_res.status_code, 200)
        self.assertIn("history", hist_res.json())

        # 3. Test Webhook
        test_res = self.client.post(
            "/api/v1/webhooks/test",
            json={"event": "ping.test", "data": {"msg": "hello"}},
            headers=self.auth_headers,
        )
        self.assertEqual(test_res.status_code, 200)
        self.assertEqual(test_res.json()["status"], "ok")

    @patch.object(llm_client, "complete", new_callable=AsyncMock)
    def test_anthropic_messages_non_streaming(self, mock_complete):
        mock_complete.return_value = CompletionResponse(
            id="resp-test-123",
            provider="anthropic",
            content="Hello from Claude translation!",
            model="anthropic/claude-3-5-sonnet",
            prompt_tokens=15,
            completion_tokens=10,
            cost_usd=0.0001,
        )

        payload = {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Hi"}],
            "system": "Be concise",
            "max_tokens": 100,
        }

        res = self.client.post("/v1/messages", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["type"], "message")
        self.assertEqual(data["role"], "assistant")
        self.assertEqual(data["model"], "claude-3-5-sonnet")
        self.assertEqual(data["content"][0]["text"], "Hello from Claude translation!")
        self.assertEqual(data["usage"]["input_tokens"], 15)
        self.assertEqual(data["usage"]["output_tokens"], 10)

    def test_anthropic_messages_streaming(self):
        async def mock_stream_gen(*args, **kwargs):
            yield StreamChunk(content="Hello ", model="claude-3-5-sonnet", provider="anthropic")
            yield StreamChunk(content="world!", model="claude-3-5-sonnet", provider="anthropic")

        with patch.object(llm_client, "stream", side_effect=mock_stream_gen):
            payload = {
                "model": "claude-3-5-sonnet",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            }

            res = self.client.post("/v1/messages", json=payload)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.headers["content-type"], "text/event-stream; charset=utf-8")
            body = res.text
            self.assertIn("event: message_start", body)
            self.assertIn("event: content_block_start", body)
            self.assertIn("event: content_block_delta", body)
            self.assertIn("Hello ", body)
            self.assertIn("event: message_delta", body)
            self.assertIn("event: message_stop", body)


if __name__ == "__main__":
    unittest.main()
