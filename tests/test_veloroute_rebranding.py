import os
import unittest
from starlette.testclient import TestClient

import veloroute
from veloroute import (
    VeloRoute,
    RoutingStrategy,
    VeloRouteError,
)
import veloroute.cli
import veloroute.client
import veloroute.gateway.keys
from veloroute.ui.app import app


class TestVeloRouteRebranding(unittest.TestCase):
    def test_imports_and_structure(self):
        self.assertTrue(hasattr(veloroute, "__version__"))
        self.assertIsNotNone(veloroute.cli.main)
        self.assertIsNotNone(veloroute.client.VeloRoute)
        self.assertIsNotNone(VeloRoute)
        self.assertIsNotNone(VeloRouteError)

    def test_submodule_access(self):
        import veloroute.core.router as vr_router
        import veloroute.gateway.keys as vr_keys
        import veloroute.storage.backends.sql as vr_sql
        self.assertIsNotNone(vr_router)
        self.assertIsNotNone(vr_keys)
        self.assertIsNotNone(vr_sql)
        self.assertIs(veloroute.storage.backends.sql, vr_sql)

    def test_environment_variables(self):
        os.environ["VELOROUTE_PROXY"] = "http://proxy.veloroute.internal:8080"
        try:
            client = VeloRoute()
            self.assertEqual(client.proxy, "http://proxy.veloroute.internal:8080")
        finally:
            os.environ.pop("VELOROUTE_PROXY", None)

    def test_dashboard_ui_branding(self):
        client = TestClient(app)
        res = client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text
        self.assertIn("<title>VeloRoute</title>", html)
        self.assertIn("⚡ VeloRoute", html)
        self.assertIn("VeloRoute - Universal AI Gateway &amp; High-Availability Routing", html)
        self.assertIn("YOUR_VELOROUTE_KEY", html)
        self.assertIn("VeloRoute exposes an OpenAI", html)
        self.assertIn("sk-velo-", html)
        self.assertIn("VeloRoute Gateway Base URL", html)
        self.assertIn("VeloRoute Test Console", html)
        self.assertIn("VeloRoute Routing Strategy", html)
        self.assertIn("VeloRoute Prompt Hub &amp; Playground", html)
        self.assertIn("VeloRoute Semantic Prompt Cache Hub", html)
        # Ensure legacy brand name is completely absent from user-facing dashboard html
        legacy_brand = "llm" + "cycle"
        self.assertNotIn(legacy_brand, html.lower())

    def test_templates_direct_resolution(self):
        from veloroute.ui.app import templates
        template_names = [
            "base.html",
            "index.html",
            "topbar.html",
            "overview.html",
            "console.html",
            "modals.html",
            "routing.html",
            "cache.html",
            "prompts.html",
            "virtual_keys.html",
            "scripts.html",
        ]
        for tname in template_names:
            tpl = templates.get_template(tname)
            self.assertIsNotNone(tpl)


if __name__ == "__main__":
    unittest.main()
