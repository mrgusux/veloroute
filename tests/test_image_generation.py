import unittest
from unittest.mock import AsyncMock, patch

import httpx

from veloroute.providers.openai_compatible import OpenAICompatibleProvider


class TestOpenAICompatibleImageGeneration(unittest.IsolatedAsyncioTestCase):
    async def test_posts_openai_image_payload_and_returns_json_unchanged(self):
        provider = OpenAICompatibleProvider(
            "https://images.example/v1", provider_name="images"
        )
        expected = {"created": 1700000000, "data": [{"b64_json": "abc123"}]}
        response = httpx.Response(
            200,
            json=expected,
            request=httpx.Request("POST", "https://images.example/v1/images/generations"),
        )
        client = AsyncMock()
        client.post.return_value = response
        with patch.object(provider, "_get_client", return_value=client):
            result = await provider.image_generations(
                {
                    "model": "dall-e-3",
                    "prompt": "A quiet library at dawn",
                    "n": 1,
                    "size": "1024x1024",
                },
                api_key="provider-secret",
            )

        self.assertEqual(result, expected)
        client.post.assert_awaited_once()
        args, kwargs = client.post.await_args
        self.assertEqual(args[0], "https://images.example/v1/images/generations")
        self.assertEqual(kwargs["json"]["model"], "dall-e-3")
        self.assertEqual(kwargs["json"]["prompt"], "A quiet library at dawn")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer provider-secret")


if __name__ == "__main__":
    unittest.main()
