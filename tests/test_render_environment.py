import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("renderer", ROOT / "scripts/render-environment.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class EnvironmentRenderingTests(unittest.TestCase):
    def test_backend_uses_discovered_group(self):
        source = (ROOT / "k8s/backend/backend.yml").read_text()
        result = renderer.render("backend", source, {"BACKEND_ALB_SECURITY_GROUP_ID": "sg-0123456789abcdef0"})
        self.assertIn("security-groups: sg-0123456789abcdef0", result)
        self.assertNotIn("REPLACE_BACKEND", result)
        self.assertNotIn("alb.ingress.kubernetes.io/subnets:", result)

    def test_gateway_uses_current_internal_hostname(self):
        source = (ROOT / "k8s/gateway/gateway.yml").read_text()
        url = "http://internal-k8s-newbackend-123.eu-north-1.elb.amazonaws.com"
        result = renderer.render("gateway", source, {"BACKEND_URL": url})
        self.assertIn(url, result)
        self.assertNotIn("backend.invalid", result)

    def test_missing_or_multiple_groups_are_rejected(self):
        for value in ("", "None", "sg-0123456789abcdef0 sg-1123456789abcdef0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                renderer.render("backend", "REPLACE_BACKEND_ALB_SECURITY_GROUP_ID", {"BACKEND_ALB_SECURITY_GROUP_ID": value})

    def test_invalid_external_or_injected_url_is_rejected(self):
        for value in ("http://", "http://example.com", "http://public.eu-north-1.elb.amazonaws.com",
                      "http://internal-test.eu-north-1.elb.amazonaws.com\nmalformed: yaml"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                renderer.render("gateway", "http://backend.invalid", {"BACKEND_URL": value})

    def test_missing_or_duplicate_marker_is_rejected(self):
        for source in ("already rendered", "http://backend.invalid http://backend.invalid"):
            with self.assertRaises(ValueError):
                renderer.render("gateway", source, {"BACKEND_URL": "http://internal-test.eu-north-1.elb.amazonaws.com"})


if __name__ == "__main__":
    unittest.main()
