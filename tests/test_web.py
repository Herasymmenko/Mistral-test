from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from fastapi.testclient import TestClient  # noqa: E402

from docdecision.web import create_app  # noqa: E402


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def post_sample(self, name: str, route: str = "/decide"):
        path = PROJECT / "samples" / name
        return self.client.post(
            route,
            files={"file": (name, io.BytesIO(path.read_bytes()), "application/octet-stream")},
        )

    def test_index_serves_upload_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('type="file"', response.text)
        self.assertIn("text/html", response.headers["content-type"])

    def test_invoice_upload_returns_decision(self):
        response = self.post_sample("invoice_small.txt")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["decision"], "approve")
        self.assertEqual(payload["rule"], "small-invoice-auto-approve")
        self.assertEqual(payload["source"], "invoice_small.txt")
        self.assertEqual(payload["fields"]["amount"], 412.9)

    def test_claim_upload_routes_through_any_of_rule(self):
        response = self.post_sample("claim_missing_number.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "request_more_info")

    def test_alias_route_matches_primary(self):
        response = self.post_sample("invoice_large.txt", route="/api/decide")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "escalate")

    def test_unsupported_suffix_maps_to_400(self):
        response = self.client.post(
            "/decide",
            files={"file": ("notes.docx", io.BytesIO(b"junk"), "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("unsupported document type", response.json()["detail"])

    def test_empty_file_still_gets_default_decision(self):
        response = self.client.post(
            "/decide", files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "needs_review")

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_custom_rules_path_is_respected(self):
        client = TestClient(create_app(rules_path=PROJECT / "rules.yaml"))
        response = client.post(
            "/decide",
            files={
                "file": (
                    "invoice_small.txt",
                    io.BytesIO((PROJECT / "samples" / "invoice_small.txt").read_bytes()),
                    "text/plain",
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "approve")


if __name__ == "__main__":
    unittest.main()
