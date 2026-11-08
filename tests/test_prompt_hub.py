import unittest
from starlette.testclient import TestClient

from veloroute.core.prompts import PromptRegistry, PromptVersion
from veloroute.ui.app import app
from veloroute.ui.routes.deps import SESSION_TOKEN, llm_client


class TestPromptHub(unittest.TestCase):
    def setUp(self):
        self.registry = PromptRegistry()
        self.client = TestClient(app)
        self.auth_headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}

    def tearDown(self):
        llm_client.virtual_keys._keys.clear()
        llm_client.virtual_keys._by_hash.clear()
        llm_client.virtual_keys.set_enforced(False)

    def test_core_prompt_registry(self):
        # 1. Verify default seeded templates
        seeded = self.registry.list_prompts_overview()
        names = [p["name"] for p in seeded]
        self.assertIn("code_refactor", names)
        self.assertIn("smart_summarizer", names)

        # 2. Register custom versioned prompt
        pv = self.registry.set(
            name="welcome_bot",
            template="Hello {{user}}, welcome to {{service}}!",
            system_prompt="You are a warm assistant for {{service}}.",
            version="v1",
            model="mock/mock-fast",
            description="Welcome message template",
        )
        self.assertEqual(pv.name, "welcome_bot")
        self.assertEqual(pv.version, "v1")
        self.assertListEqual(sorted(pv.variables()), ["service", "user"])

        # 3. Render template and messages
        rendered = self.registry.render("welcome_bot", user="Alice", service="VeloRoute")
        self.assertEqual(rendered, "Hello Alice, welcome to VeloRoute!")

        messages = self.registry.render_messages("welcome_bot", user="Alice", service="VeloRoute")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "You are a warm assistant for VeloRoute.")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "Hello Alice, welcome to VeloRoute!")

        # 4. Missing variable raises KeyError
        with self.assertRaises(KeyError):
            self.registry.render("welcome_bot", user="Alice")

        # 5. Add version v2
        pv2 = self.registry.set(
            name="welcome_bot",
            template="Hey {{user}}, glad you joined {{service}} today!",
            version="v2",
        )
        self.assertEqual(pv2.version, "v2")
        self.assertEqual(self.registry.get("welcome_bot").version, "v2")
        self.assertEqual(self.registry.get("welcome_bot", version="v1").version, "v1")

        # 6. Delete version v1
        del_count = self.registry.delete("welcome_bot", version="v1")
        self.assertEqual(del_count, 1)
        self.assertEqual(len(self.registry.list(name="welcome_bot")), 1)

    def test_api_prompt_endpoints(self):
        # 1. List prompts
        res = self.client.get("/api/v1/prompts", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertGreaterEqual(data["total"], 1)

        # 2. Create new prompt via API
        res_create = self.client.post(
            "/api/v1/prompts",
            headers=self.auth_headers,
            json={
                "name": "tester_agent",
                "template": "Write unit tests in {{framework}} for this logic: {{code}}",
                "system_prompt": "You are a QA automation expert in {{framework}}.",
                "version": "v1",
                "description": "Automated unit test generator",
                "model": "mock/mock-fast",
            },
        )
        self.assertEqual(res_create.status_code, 201)
        created_data = res_create.json()
        self.assertEqual(created_data["prompt"]["name"], "tester_agent")
        self.assertIn("framework", created_data["prompt"]["variables"])
        self.assertIn("code", created_data["prompt"]["variables"])

        # 3. Preview/Render endpoint
        res_render = self.client.post(
            "/api/v1/prompts/tester_agent/render",
            headers=self.auth_headers,
            json={"variables": {"framework": "pytest", "code": "def add(a, b): return a + b"}},
        )
        self.assertEqual(res_render.status_code, 200)
        render_data = res_render.json()
        self.assertIn("pytest", render_data["messages"][0]["content"])
        self.assertIn("def add", render_data["messages"][1]["content"])

        # 4. Execute prompt endpoint in playground
        res_run = self.client.post(
            "/api/v1/prompts/tester_agent/run",
            headers=self.auth_headers,
            json={
                "variables": {"framework": "pytest", "code": "def add(a, b): return a + b"},
                "model": "mock/mock-fast",
            },
        )
        self.assertEqual(res_run.status_code, 200)
        run_data = res_run.json()
        self.assertEqual(run_data["status"], "ok")
        self.assertIn("content", run_data)
        self.assertGreaterEqual(run_data["tokens"], 1)

        # 5. Delete prompt
        res_del = self.client.delete("/api/v1/prompts/tester_agent", headers=self.auth_headers)
        self.assertEqual(res_del.status_code, 200)


if __name__ == "__main__":
    unittest.main()
