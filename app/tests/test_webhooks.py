"""Lead-capture webhook and outbound webhook steps."""
import asyncio
import json
import unittest
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.services import webhooks
from app.tests.test_consolidation import _TenantClient


def _phone() -> str:
    return "+9193" + str(uuid.uuid4().int)[:8]


class TestWebhooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def _hook(self, owner) -> tuple[str, str]:
        res = owner.post("/api/integrations/webhook/rotate")
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["url"].split("/api/hooks/leads/")[1], res.json()["signing_secret"]

    def test_capture_creates_then_enriches_a_lead(self):
        owner = _TenantClient(self.client)
        owner.post("/api/crm/fields", json={"label": "Source page", "field_type": "text"})
        wf = owner.post("/api/crm/workflows", json={"name": "Hook", "trigger_event": "webhook_received",
                                                     "actions": [{"type": "create_reminder", "config": {"text": "Call the web lead"}}]}).json()
        token, _ = self._hook(owner)
        phone = _phone()
        first = self.client.post(f"/api/hooks/leads/{token}", json={"name": "Web Lead", "phone": phone, "email": "",
                                                                     "custom_fields": {"source_page": "/pricing"}})
        self.assertEqual(first.status_code, 202, first.text)
        self.assertTrue(first.json()["created"])
        again = self.client.post(f"/api/hooks/leads/{token}", json={"name": "Other name", "phone": phone, "email": "w@example.com", "notes": "Second form"})
        self.assertFalse(again.json()["created"])
        lead = next(l for l in owner.get("/api/crm/leads").json() if l["phone"] == phone)
        self.assertEqual((lead["name"], lead["email"], lead["custom_fields"]), ("Web Lead", "w@example.com", {"source_page": "/pricing"}))
        from app.tests.test_voice_bookings_and_events import _drain
        _drain()
        self.assertEqual(len(owner.get(f"/api/crm/workflows/{wf['id']}/runs").json()), 2)

    def test_bad_requests_and_rotation(self):
        owner = _TenantClient(self.client)
        token, _ = self._hook(owner)
        self.assertEqual(self.client.post("/api/hooks/leads/not-a-token", json={"name": "X", "phone": _phone()}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/hooks/leads/{token}", json={"name": "X", "phone": "abc"}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/hooks/leads/{token}", content=b"x" * (70 * 1024)).status_code, 413)
        new_token, _ = self._hook(owner)
        self.assertEqual(self.client.post(f"/api/hooks/leads/{token}", json={"name": "X", "phone": _phone()}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/hooks/leads/{new_token}", json={"name": "X", "phone": _phone()}).status_code, 202)
        status = owner.get("/api/integrations/webhook").json()
        self.assertTrue(status["configured"])
        self.assertIsNotNone(status["last_used_at"])
        self.assertEqual(owner.delete("/api/integrations/webhook").status_code, 204)
        self.assertEqual(self.client.post(f"/api/hooks/leads/{new_token}", json={"name": "X", "phone": _phone()}).status_code, 404)

    def test_url_safety(self):
        for url in ("http://127.0.0.1/hook", "http://169.254.169.254/latest", "http://10.0.0.5/x", "ftp://example.com/x", "http://localhost:8000/x"):
            with self.assertRaises(webhooks.UnsafeUrl, msg=url):
                webhooks.check_public_url(url)
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.1.2.3", 443))]):
            with self.assertRaises(webhooks.UnsafeUrl):  # public-looking name that resolves inside
                webhooks.check_public_url("https://sneaky.example.com/x")

    def test_workflow_step_posts_a_signed_event(self):
        from app.services.workflow_engine import workflow_engine
        owner = _TenantClient(self.client)
        _, secret = self._hook(owner)
        owner.post("/api/crm/workflows", json={"name": "Notify", "trigger_event": "lead_created",
                                                "actions": [{"type": "call_webhook", "config": {"url": "https://hooks.example.com/avn"}}]})
        lead = owner.post("/api/crm/leads", json={"name": "Signed", "phone": _phone()}).json()
        sent = {}

        def fake_post(url, content, headers, timeout, follow_redirects):
            sent.update(url=url, body=content, headers=headers, follow_redirects=follow_redirects)
            return MagicMock(status_code=200)

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch("httpx.post", side_effect=fake_post):
            asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], owner.tenant_id))
        self.assertFalse(sent["follow_redirects"])
        self.assertEqual(sent["headers"]["X-AVN-Signature"], webhooks.sign(secret, sent["body"]))
        body = json.loads(sent["body"])
        self.assertEqual((body["event"], body["lead"]["id"], body["workspace_id"]), ("workflow.step", lead["id"], owner.tenant_id))
        wf = owner.get("/api/crm/workflows").json()[0]
        self.assertIn("webhook answered 200", owner.get(f"/api/crm/workflows/{wf['id']}/runs").json()[0]["message"])

    def test_only_admins_manage_the_webhook(self):
        owner = _TenantClient(self.client)
        email = f"m-{uuid.uuid4().hex[:6]}@example.com"
        with patch("app.routers.team.deliver", return_value="logged"):
            token = owner.post("/api/team/invitations", json={"email": email, "role": "Manager"}).json()["accept_url"].split("token=")[1]
        access = self.client.post("/api/auth/invitations/accept", json={"token": token, "name": "M", "password": "correct-horse-1"}).json()["access_token"]
        self.assertEqual(self.client.post("/api/integrations/webhook/rotate", headers={"Authorization": f"Bearer {access}"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
