"""The workspace's iCalendar feed, and SMS through Twilio (sending and the "Send SMS" workflow step)."""
import asyncio
import base64
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.lead import LeadActivity
from app.services import sms
from app.services.workflow_engine import workflow_engine
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member


def _phone() -> str:
    return "+9194" + str(uuid.uuid4().int)[:8]


class TestIcalFeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def book(self, owner, days, name="Meera; Iyer, Jr", notes=None):
        start = (datetime.now(timezone.utc) + timedelta(days=days)).replace(second=0, microsecond=0)
        body = {"contact_name": name, "contact_phone": _phone(), "timezone": "UTC", "title": "Consultation",
                "scheduled_start": start.strftime("%Y-%m-%dT%H:%M"), "scheduled_end": (start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")}
        if notes:
            body["notes"] = notes
        res = owner.post("/api/appointments", json=body)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def test_feed_is_off_until_turned_on_and_admin_only(self):
        owner = _TenantClient(self.client)
        self.assertFalse(owner.get("/api/integrations/ical-feed").json()["enabled"])
        self.assertEqual(_Member(self.client, owner, "Manager").post("/api/integrations/ical-feed/rotate").status_code, 403)
        feed = owner.post("/api/integrations/ical-feed/rotate").json()
        self.assertTrue(feed["enabled"])
        self.assertTrue(feed["webcal_url"].startswith("webcal://"))
        self.assertTrue(feed["url"].endswith(".ics"))

    def test_feed_contents(self):
        owner = _TenantClient(self.client)
        apt = self.book(owner, 3, notes="Wants a window seat. " + "x" * 120)
        cancelled = self.book(owner, 4, name="Ravi")
        owner.post(f"/api/appointments/{cancelled['id']}/cancel", json={})
        other = _TenantClient(self.client)
        self.book(other, 3, name="Someone Else")
        path = "/" + owner.post("/api/integrations/ical-feed/rotate").json()["url"].split("/", 3)[3]
        res = self.client.get(path)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["content-type"].startswith("text/calendar"))
        text = res.text
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n"))
        self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")), "lines are folded at 75 octets")
        unfolded = text.replace("\r\n ", "")
        self.assertIn(f"UID:{apt['id']}@avn", unfolded)
        self.assertIn("SUMMARY:Consultation: Meera\\; Iyer\\, Jr", unfolded)
        self.assertIn("\\n\\nWants a window seat.", unfolded)
        self.assertIn(f"DTSTART:{datetime.fromisoformat(apt['scheduled_start']).strftime('%Y%m%dT%H%M%SZ')}", unfolded)
        self.assertEqual(unfolded.count("STATUS:CANCELLED"), 1)
        self.assertNotIn("Someone Else", unfolded)

    def test_rotating_or_turning_off_cuts_old_links(self):
        owner = _TenantClient(self.client)
        first = "/" + owner.post("/api/integrations/ical-feed/rotate").json()["url"].split("/", 3)[3]
        second = "/" + owner.post("/api/integrations/ical-feed/rotate").json()["url"].split("/", 3)[3]
        self.assertEqual(self.client.get(first).status_code, 404)
        self.assertEqual(self.client.get(second).status_code, 200)
        self.assertEqual(owner.delete("/api/integrations/ical-feed").status_code, 204)
        self.assertEqual(self.client.get(second).status_code, 404)
        self.assertEqual(self.client.get("/api/ical/made-up-token.ics").status_code, 404)


class FakeTwilio:
    def __init__(self):
        self.sent: list[dict] = []
        self.fail = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != "Basic " + base64.b64encode(b"AC1:tok").decode():
            return httpx.Response(401, json={"message": "Authenticate"})
        if request.method == "GET":
            return httpx.Response(200, json={"status": "active"})
        if self.fail:
            return httpx.Response(400, json={"message": self.fail})
        self.sent.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(201, json={"sid": "SM" + uuid.uuid4().hex})


class TestSms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.twilio = FakeTwilio()
        for p in (patch.object(sms, "http", lambda: httpx.Client(transport=httpx.MockTransport(self.twilio))),
                  patch.dict(os.environ, {"SECRETS_ENCRYPTION_KEY": Fernet.generate_key().decode()})):
            p.start()
            self.addCleanup(p.stop)
        self.owner = _TenantClient(self.client)

    def connect(self):
        res = self.owner.put("/api/integrations/sms", json={"account_sid": "AC1", "auth_token": "tok", "from_number": "+1 415 555 0101"})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def test_connect_and_send(self):
        self.assertEqual(self.owner.post("/api/crm/sms", json={"phone": _phone(), "text": "hi"}).status_code, 501)
        bad = self.owner.put("/api/integrations/sms", json={"account_sid": "AC1", "auth_token": "wrong", "from_number": "+14155550101"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.connect()["sender"], "+14155550101")
        lead = self.owner.post("/api/crm/leads", json={"name": "Asha", "phone": _phone()}).json()
        res = self.owner.post("/api/crm/sms", json={"lead_id": lead["id"], "text": "Your appointment is tomorrow at 10."})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self.twilio.sent[-1], {"From": "+14155550101", "To": lead["phone"], "Body": "Your appointment is tomorrow at 10."})
        db = SessionLocal()
        try:
            self.assertEqual([a.title for a in db.query(LeadActivity).filter(LeadActivity.lead_id == lead["id"],
                                                                             LeadActivity.activity_type == "sms")], ["SMS sent"])
        finally:
            db.close()
        self.twilio.fail = "The 'To' number is not a valid phone number."
        failed = self.owner.post("/api/crm/sms", json={"lead_id": lead["id"], "text": "again"})
        self.assertEqual(failed.status_code, 502)
        self.assertIn("not a valid phone number", failed.json()["detail"])
        self.assertEqual(self.owner.delete("/api/integrations/sms").status_code, 204)
        self.assertFalse(self.owner.get("/api/integrations/sms").json()["connected"])

    def test_workflow_step_with_placeholders(self):
        self.connect()
        wf = self.owner.post("/api/crm/workflows", json={"name": "Welcome text", "trigger_event": "lead_created",
                                                        "actions": [{"type": "send_sms", "config": {"message": "Hi {{lead.first_name}}, thanks for calling {{workspace.name}}!"}}]}).json()
        lead = self.owner.post("/api/crm/leads", json={"name": "Kavya Rao", "phone": _phone()}).json()
        asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], self.owner.tenant_id))
        self.assertEqual(self.twilio.sent[-1]["Body"], "Hi Kavya, thanks for calling Co!")
        self.assertEqual(self.owner.get(f"/api/crm/workflows/{wf['id']}/runs").json()[0]["status"], "success")

    def test_other_workspaces_and_roles(self):
        self.connect()
        lead = self.owner.post("/api/crm/leads", json={"name": "Asha", "phone": _phone()}).json()
        other = _TenantClient(self.client)
        self.assertEqual(other.post("/api/crm/sms", json={"lead_id": lead["id"], "text": "hi"}).status_code, 404)
        self.assertFalse(other.get("/api/integrations/sms").json()["connected"])
        agent = _Member(self.client, self.owner, "Agent")
        self.assertEqual(agent.put("/api/integrations/sms", json={"account_sid": "AC1", "auth_token": "tok", "from_number": "+14155550101"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
