"""Unit tests for Gateway Transformation & Custom Middleware Engine."""
import unittest
from veloroute.core.transform import TransformManager, TransformRule


class TestTransformManager(unittest.TestCase):
    def setUp(self):
        self.mgr = TransformManager(persistence_path="test_transforms.json")
        # Clean any extra rules
        self.mgr._rules.clear()

    def tearDown(self):
        import os
        if os.path.exists("test_transforms.json"):
            os.remove("test_transforms.json")

    def test_model_rewrite(self):
        rule = TransformRule(
            id="rule-model-1",
            name="Rewrite gpt-3.5 to gpt-4o-mini",
            rule_type="model_rewrite",
            match_pattern="gpt-3.5*",
            replacement="openai/gpt-4o-mini",
            enabled=True,
        )
        self.mgr.add_rule(rule)

        self.assertEqual(
            self.mgr.transform_model("gpt-3.5-turbo"),
            "openai/gpt-4o-mini",
        )
        self.assertEqual(
            self.mgr.transform_model("gpt-3.5-turbo-16k"),
            "openai/gpt-4o-mini",
        )
        self.assertEqual(
            self.mgr.transform_model("openai/gpt-4o"),
            "openai/gpt-4o",
        )

    def test_request_header_injection(self):
        rule = TransformRule(
            id="rule-hdr-1",
            name="Inject Org ID",
            rule_type="inject_header",
            match_pattern="X-Gateway-Org",
            replacement="Enterprise-99",
            enabled=True,
        )
        self.mgr.add_rule(rule)

        original = {"Content-Type": "application/json"}
        transformed = self.mgr.transform_request_headers(original)
        self.assertEqual(transformed["X-Gateway-Org"], "Enterprise-99")
        self.assertEqual(transformed["Content-Type"], "application/json")

    def test_response_header_stripping(self):
        rule = TransformRule(
            id="rule-strip-1",
            name="Strip server header",
            rule_type="strip_header",
            match_pattern="server",
            replacement="",
            enabled=True,
        )
        self.mgr.add_rule(rule)

        original = {
            "Server": "cloudflare",
            "Content-Type": "application/json",
            "X-Request-Id": "123",
        }
        transformed = self.mgr.transform_response_headers(original)
        self.assertNotIn("Server", transformed)
        self.assertIn("Content-Type", transformed)
        self.assertIn("X-Request-Id", transformed)

    def test_response_text_redaction(self):
        rule = TransformRule(
            id="rule-redact-1",
            name="Redact secret codename",
            rule_type="response_redact",
            match_pattern="ProjectTitan",
            replacement="[CONFIDENTIAL_PROJECT]",
            enabled=True,
        )
        self.mgr.add_rule(rule)

        raw = "Welcome to ProjectTitan. The budget for ProjectTitan is $1M."
        redacted = self.mgr.transform_response_text(raw)
        self.assertEqual(
            redacted,
            "Welcome to [CONFIDENTIAL_PROJECT]. The budget for [CONFIDENTIAL_PROJECT] is $1M.",
        )

    def test_sandbox_testing(self):
        rule = TransformRule(
            id="rule-redact-2",
            name="Redact competitor",
            rule_type="response_redact",
            match_pattern="CompetitorX",
            replacement="[REDACTED]",
            enabled=True,
        )
        self.mgr.add_rule(rule)

        res = self.mgr.test_transform("redact", "Powered by CompetitorX")
        self.assertTrue(res["modified"])
        self.assertEqual(res["transformed"], "Powered by [REDACTED]")


if __name__ == "__main__":
    unittest.main()
