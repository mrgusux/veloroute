import unittest
import asyncio
from starlette.testclient import TestClient

from veloroute.gateway.keys import VirtualKeyManager
from veloroute.ui.app import app
from veloroute.ui.routes.deps import SESSION_TOKEN, llm_client


class TestVirtualKeyBudgetAlerts(unittest.TestCase):
    def setUp(self):
        self.mgr = VirtualKeyManager()
        self.client = TestClient(app)
        self.auth_headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}

    def tearDown(self):
        llm_client.virtual_keys._keys.clear()
        llm_client.virtual_keys._by_hash.clear()
        llm_client.virtual_keys.set_enforced(False)

    def test_budget_alert_threshold_and_auto_pause(self):
        async def run():
            # 1. Create key with $10.00 budget and 80% alert threshold
            record, raw_key = await self.mgr.create_key(
                "budget-worker",
                budget_usd=10.0,
                budget_alert_threshold=0.80,
                budget_alert_webhook="http://127.0.0.1:9999/test-webhook",
                auto_pause_on_budget=True,
            )
            self.assertEqual(record.budget_usd, 10.0)
            self.assertEqual(record.budget_alert_threshold, 0.80)
            self.assertTrue(record.auto_pause_on_budget)
            self.assertFalse(record.alert_sent)
            self.assertTrue(record.enabled)

            # 2. Spend $5.00 (50%) -> Under 80% threshold
            await self.mgr.record_usage(record.id, cost_usd=5.00)
            rec = self.mgr.get_key(record.id)
            self.assertEqual(rec.spent_usd, 5.00)
            self.assertFalse(rec.alert_sent)
            self.assertTrue(rec.enabled)

            # 3. Spend another $3.50 -> Total $8.50 (85%) -> Crosses 80% threshold!
            await self.mgr.record_usage(record.id, cost_usd=3.50)
            rec = self.mgr.get_key(record.id)
            self.assertEqual(rec.spent_usd, 8.50)
            self.assertTrue(rec.alert_sent)
            self.assertTrue(rec.enabled)

            # 4. Spend another $1.50 -> Total $10.00 (100%) -> Exhausts budget!
            await self.mgr.record_usage(record.id, cost_usd=1.50)
            rec = self.mgr.get_key(record.id)
            self.assertEqual(rec.spent_usd, 10.00)
            # Must be auto-paused!
            self.assertFalse(rec.enabled)
            self.assertFalse(rec.is_active)

            # 5. Public dict includes percent and threshold
            pub = rec.to_public_dict()
            self.assertEqual(pub["spent_percent"], 100.0)
            self.assertEqual(pub["budget_alert_threshold"], 0.80)
            self.assertTrue(pub["alert_sent"])

            # 6. Update key increases budget to $20.00 -> unpauses and resets alert
            updated = await self.mgr.update_key(record.id, budget_usd=20.0, enabled=True)
            self.assertEqual(updated.budget_usd, 20.0)
            self.assertTrue(updated.enabled)
            self.assertFalse(updated.alert_sent)
            self.assertEqual(updated.to_public_dict()["spent_percent"], 50.0)

        asyncio.run(run())

    def test_api_virtual_key_budget_alert_endpoints(self):
        # 1. Create key via API
        res = self.client.post(
            "/api/v1/gateway/keys",
            headers=self.auth_headers,
            json={
                "name": "enterprise-client",
                "budget_usd": 25.0,
                "budget_alert_threshold": 0.75,
                "budget_alert_webhook": "https://example.com/alerts",
                "auto_pause_on_budget": True,
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        vk = data["virtual_key"]
        self.assertEqual(vk["name"], "enterprise-client")
        self.assertEqual(vk["budget_usd"], 25.0)
        self.assertEqual(vk["budget_alert_threshold"], 0.75)
        self.assertEqual(vk["budget_alert_webhook"], "https://example.com/alerts")
        self.assertTrue(vk["auto_pause_on_budget"])

        key_id = vk["id"]

        # 2. Patch key via API
        res_patch = self.client.patch(
            f"/api/v1/gateway/keys/{key_id}",
            headers=self.auth_headers,
            json={
                "budget_alert_threshold": 0.90,
                "auto_pause_on_budget": False,
            },
        )
        self.assertEqual(res_patch.status_code, 200)
        updated_vk = res_patch.json()["virtual_key"]
        self.assertEqual(updated_vk["budget_alert_threshold"], 0.90)
        self.assertFalse(updated_vk["auto_pause_on_budget"])


if __name__ == "__main__":
    unittest.main()
