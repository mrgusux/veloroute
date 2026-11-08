import asyncio
import os
import sys
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from starlette.requests import Request
from starlette.testclient import TestClient

from veloroute.gateway.keys import GatewayAuthError, VirtualKeyManager
from veloroute.core.errors import RateLimitError
from veloroute.schema import CompletionResponse
from veloroute.ui.app import app
from veloroute.ui.routes.deps import SESSION_TOKEN, llm_client
from veloroute.ui.routes.proxy import openai_proxy_chat_completions


class TestVirtualKeyReservations(unittest.IsolatedAsyncioTestCase):
    async def test_scoped_key_requires_an_explicit_model_check(self):
        manager = VirtualKeyManager(enforce=True)
        _, raw_key = await manager.create_key(
            "scoped", allowed_models=["openai/gpt-4o"]
        )

        with self.assertRaises(GatewayAuthError) as raised:
            await manager.authorize(raw_key)
        self.assertEqual(raised.exception.code, "model_not_allowed")

    async def test_budgeted_key_rejects_models_without_pricing(self):
        manager = VirtualKeyManager(enforce=True)
        _, raw_key = await manager.create_key(
            "budgeted",
            budget_usd=5,
            allowed_models=["custom/model"],
        )

        with self.assertRaises(GatewayAuthError) as raised:
            await manager.authorize_with_reservation(
                raw_key,
                model="custom/model",
                budget_pricing_available=False,
            )
        self.assertEqual(raised.exception.code, "unpriced_model")
        self.assertFalse(manager._windows)

    async def test_actual_usage_replaces_token_estimate(self):
        manager = VirtualKeyManager(enforce=True)
        record, raw_key = await manager.create_key("limited", tpm_limit=10)

        authorized, reservation_id = await manager.authorize_with_reservation(
            raw_key,
            model="openai/gpt-4o",
            estimated_tokens=8,
        )
        await manager.record_usage(
            authorized.id,
            prompt_tokens=2,
            reservation_id=reservation_id,
            reserved_tokens=8,
        )

        # A new request fits against the reconciled actual count (2 + 8 = 10).
        _, next_reservation = await manager.authorize_with_reservation(
            raw_key,
            model="openai/gpt-4o",
            estimated_tokens=8,
        )
        self.assertTrue(next_reservation)

    async def test_saved_keys_reload_without_storing_plaintext(self):
        class MemoryConfigStore:
            def __init__(self):
                self.config = None

            async def save_config(self, name, value):
                self.config = SimpleNamespace(value=value)

            async def get_config(self, name):
                return self.config

        storage = MemoryConfigStore()
        manager = VirtualKeyManager(storage=storage)
        _, raw_key = await manager.create_key("persistent")
        self.assertNotIn(raw_key, repr(storage.config.value))

        restarted_manager = VirtualKeyManager(storage=storage)
        self.assertEqual(await restarted_manager.load(), 1)
        self.assertTrue(restarted_manager.enforcement_enabled)
        authorized = await restarted_manager.authorize(raw_key)
        self.assertEqual(authorized.name, "persistent")

    async def test_nullable_limits_can_be_cleared(self):
        manager = VirtualKeyManager(enforce=True)
        record, _ = await manager.create_key(
            "clearable", budget_usd=5, rpm_limit=30, tpm_limit=1000,
            allowed_models=["openai/gpt-4o"],
        )

        updated = await manager.update_key(
            record.id,
            budget_usd=None,
            rpm_limit=None,
            tpm_limit=None,
            allowed_models=[],
            expires_at=None,
        )

        self.assertIsNone(updated.budget_usd)
        self.assertIsNone(updated.rpm_limit)
        self.assertIsNone(updated.tpm_limit)
        self.assertEqual(updated.allowed_models, [])
        self.assertIsNone(updated.expires_at)


class TestStreamingGatewayCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_disconnected_client_cancels_upstream_stream(self):
        original_manager = llm_client.virtual_keys
        llm_client.virtual_keys = VirtualKeyManager(storage=None, enforce=False)
        upstream_cancelled = asyncio.Event()

        async def fake_provider_stream():
            try:
                yield "first chunk"
                await asyncio.Event().wait()
            finally:
                upstream_cancelled.set()

        def fake_client_stream(**kwargs):
            return fake_provider_stream()

        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 12345),
            "scheme": "http",
        })
        try:
            with patch.object(llm_client, "stream", new=fake_client_stream):
                response = await openai_proxy_chat_completions(
                    {
                        "model": "openai/gpt-4o",
                        "messages": [{"role": "user", "content": "hello"}],
                        "stream": True,
                    },
                    request,
                )
                iterator = response.body_iterator
                first_chunk = await anext(iterator)
                self.assertIn("first chunk", first_chunk)
                await iterator.aclose()
            self.assertTrue(upstream_cancelled.is_set())
        finally:
            llm_client.virtual_keys = original_manager

    async def test_upstream_error_is_an_sse_error_not_assistant_text(self):
        original_manager = llm_client.virtual_keys
        llm_client.virtual_keys = VirtualKeyManager(storage=None, enforce=False)

        async def failed_stream():
            yield "partial answer"
            raise RateLimitError("upstream throttled", provider="openai", status_code=429)

        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 12345),
            "scheme": "http",
        })
        try:
            with patch.object(llm_client, "stream", return_value=failed_stream()):
                response = await openai_proxy_chat_completions(
                    {"model": "openai/gpt-4o", "messages": [], "stream": True},
                    request,
                )
                frames = [frame async for frame in response.body_iterator]
            joined = "".join(frames)
            self.assertIn('"error"', joined)
            self.assertIn('"type": "RateLimitError"', joined)
            self.assertNotIn("[VeloRoute Proxy Error]", joined)
            self.assertIn("data: [DONE]", joined)
        finally:
            llm_client.virtual_keys = original_manager


class TestVirtualKeyGateway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.admin_headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}

    def setUp(self):
        self.original_manager = llm_client.virtual_keys
        llm_client.virtual_keys = VirtualKeyManager(storage=None, enforce=False)
        self.created = self.client.post(
            "/api/v1/gateway/keys",
            headers=self.admin_headers,
            json={
                "name": "test key",
                "budget_usd": 10,
                "rpm_limit": 20,
                "tpm_limit": 1000,
                "allowed_models": ["openai/gpt-4o"],
            },
        )
        self.assertEqual(self.created.status_code, 201, self.created.text)
        self.key = self.created.json()["key"]
        self.key_id = self.created.json()["virtual_key"]["id"]

    def tearDown(self):
        llm_client.virtual_keys = self.original_manager

    def test_proxy_enforces_key_and_model_scope_then_records_usage(self):
        request_body = {
            "model": "openai/gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
        }

        missing = self.client.post("/v1/chat/completions", json=request_body)
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["error"]["code"], "missing_api_key")

        denied = self.client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={**request_body, "model": "openai/gpt-4o-mini"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "model_not_allowed")

        completion = CompletionResponse(
            id="gateway-response",
            model="openai/gpt-4o",
            provider="openai",
            content="hello back",
            prompt_tokens=5,
            completion_tokens=2,
        )
        with patch.object(llm_client, "complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = completion
            response = self.client.post(
                "/v1/chat/completions",
                headers={"x-api-key": self.key},
                json=request_body,
            )

        self.assertEqual(response.status_code, 200, response.text)
        mock_complete.assert_awaited_once()
        usage = self.client.get(
            f"/api/v1/gateway/keys/{self.key_id}", headers=self.admin_headers
        ).json()["virtual_key"]
        self.assertEqual(usage["total_requests"], 1)
        self.assertEqual(usage["total_prompt_tokens"], 5)
        self.assertEqual(usage["total_completion_tokens"], 2)

        listed = self.client.get("/api/v1/gateway/keys", headers=self.admin_headers)
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("key_hash", listed.text)
        self.assertIn("window_requests", listed.json()["keys"][0])

    def test_key_management_is_admin_only_and_rotation_invalidates_old_key(self):
        unauthenticated = self.client.get("/api/v1/gateway/keys")
        self.assertEqual(unauthenticated.status_code, 401)

        rotated = self.client.post(
            f"/api/v1/gateway/keys/{self.key_id}/rotate",
            headers=self.admin_headers,
        )
        self.assertEqual(rotated.status_code, 200, rotated.text)
        replacement = rotated.json()["key"]

        with patch.object(llm_client, "get_providers", return_value=[]):
            old_key_response = self.client.get(
                "/v1/models", headers={"Authorization": f"Bearer {self.key}"}
            )
            new_key_response = self.client.get(
                "/v1/models", headers={"Authorization": f"Bearer {replacement}"}
            )
        self.assertEqual(old_key_response.status_code, 401)
        self.assertEqual(old_key_response.json()["error"]["code"], "invalid_api_key")
        self.assertEqual(new_key_response.status_code, 200)

    def test_proxy_preserves_upstream_error_status(self):
        with patch.object(
            llm_client,
            "complete",
            new_callable=AsyncMock,
            side_effect=RateLimitError(
                "upstream is throttling", provider="openai", status_code=429
            ),
        ):
            response = self.client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json={
                    "model": "openai/gpt-4o",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["type"], "RateLimitError")
        usage = llm_client.virtual_keys.get_usage(self.key_id)
        self.assertEqual(usage["total_requests"], 1)
        self.assertEqual(usage["total_tokens"], 0)
        self.assertEqual(usage["window_tokens"], 0)

    def test_budgeted_proxy_key_fails_closed_for_unpriced_models(self):
        created = self.client.post(
            "/api/v1/gateway/keys",
            headers=self.admin_headers,
            json={
                "name": "custom model budget",
                "budget_usd": 5,
                "allowed_models": ["custom/model"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        raw_key = created.json()["key"]
        with patch.object(llm_client, "_get_pricing", return_value=None):
            response = self.client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {raw_key}"},
                json={
                    "model": "custom/model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "unpriced_model")

    def test_image_generations_authorizes_and_returns_openai_payload(self):
        created = self.client.post(
            "/api/v1/gateway/keys",
            headers=self.admin_headers,
            json={"name": "image caller", "allowed_models": ["openai/gpt-image-1"]},
        )
        self.assertEqual(created.status_code, 201, created.text)
        raw_key = created.json()["key"]
        key_id = created.json()["virtual_key"]["id"]
        upstream = {"created": 1730000000, "data": [{"url": "https://img.example/result.png"}]}

        with patch.object(llm_client, "image_generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = upstream
            response = self.client.post(
                "/v1/images/generations",
                headers={"Authorization": f"Bearer {raw_key}"},
                json={"model": "openai/gpt-image-1", "prompt": "A blue bicycle", "n": 1, "size": "1024x1024"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), upstream)
        mock_generate.assert_awaited_once()
        self.assertEqual(mock_generate.await_args.kwargs["params"], {"n": 1, "size": "1024x1024"})
        usage = llm_client.virtual_keys.get_usage(key_id)
        self.assertEqual(usage["total_requests"], 1)
        self.assertGreater(usage["total_prompt_tokens"], 0)
        self.assertEqual(usage["spent_usd"], 0)

    def test_image_generation_rejects_budget_key_without_per_image_pricing(self):
        created = self.client.post(
            "/api/v1/gateway/keys",
            headers=self.admin_headers,
            json={"name": "image budget", "budget_usd": 5, "allowed_models": ["openai/gpt-image-1"]},
        )
        raw_key = created.json()["key"]
        response = self.client.post(
            "/v1/images/generations",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "openai/gpt-image-1", "prompt": "A blue bicycle"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "unpriced_model")

    def test_audio_endpoints_fail_closed_for_budgeted_keys(self):
        created = self.client.post(
            "/api/v1/gateway/keys",
            headers=self.admin_headers,
            json={"name": "audio budget", "budget_usd": 5},
        )
        raw_key = created.json()["key"]
        auth_headers = {"Authorization": f"Bearer {raw_key}"}
        with patch.object(llm_client, "_get_pricing", return_value={"input": 1, "output": 1}), \
             patch.object(llm_client, "audio_speech", new_callable=AsyncMock) as mock_speech, \
             patch.object(llm_client, "audio_transcribe", new_callable=AsyncMock) as mock_transcribe:
            speech = self.client.post(
                "/v1/audio/speech",
                headers=auth_headers,
                json={"model": "tts-1", "input": "hello"},
            )
            transcription = self.client.post(
                "/v1/audio/transcriptions",
                headers=auth_headers,
                data={"model": "whisper-1"},
                files={"file": ("speech.wav", b"audio bytes", "audio/wav")},
            )

        self.assertEqual(speech.status_code, 400)
        self.assertEqual(speech.json()["error"]["code"], "unpriced_model")
        self.assertEqual(transcription.status_code, 400)
        self.assertEqual(transcription.json()["error"]["code"], "unpriced_model")
        mock_speech.assert_not_awaited()
        mock_transcribe.assert_not_awaited()

    def test_dashboard_includes_virtual_key_management_screen(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="page-keys"', response.text)
        self.assertIn("Create virtual key", response.text)

    def test_cors_does_not_allow_arbitrary_origins(self):
        response = self.client.options(
            "/api/v1/gateway/keys",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_dashboard_accepts_correctly_spelled_password_setting(self):
        with patch.dict(
            os.environ,
            {
                "VELOROUTE_USER_ADMIN": "test-admin",
                "VELOROUTE_USER_ADMIN_PASSWORD": "test-secret",
            },
        ):
            response = self.client.post(
                "/api/v1/token",
                data={"username": "test-admin", "password": "test-secret"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["access_token"])


if __name__ == "__main__":
    unittest.main()
