"""CSV lead import and follow-up dates."""
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.tests.test_consolidation import _TenantClient


def _phone() -> str:
    return "+9195" + str(uuid.uuid4().int)[:8]


class TestCrmImportAndFollowUps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def _upload(self, client, text: str):
        return client.post("/api/crm/leads/import", files={"file": ("leads.csv", text.encode("utf-8"), "text/csv")})

    def test_import_creates_valid_rows_and_reports_the_rest(self):
        owner = _TenantClient(self.client)
        existing = _phone()
        owner.post("/api/crm/leads", json={"name": "Existing", "phone": existing})
        p1, p2 = _phone(), _phone()
        csv_text = (
            "Full Name,Mobile,Email,Stage,Follow Up\n"
            f"Asha,{p1[:6]} {p1[6:]},asha@example.com,Contacted,2026-12-01\n"
            f"Dup,{existing},,,\n"
            "Bad phone,12345,,,\n"
            f"Bad stage,{p2},,Whatever,\n"
            f"Repeat,{p1},,,\n"
            ",,,,\n"
        )
        res = self._upload(owner, csv_text)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["created"], 1)
        self.assertEqual([s["row"] for s in body["skipped"]], [3, 4, 5, 6])
        lead = next(l for l in owner.get("/api/crm/leads").json() if l["phone"] == p1)
        self.assertEqual((lead["status"], lead["email"], lead["follow_up_date"]), ("Contacted", "asha@example.com", "2026-12-01"))

    def test_import_needs_name_and_phone_and_manager_role(self):
        owner = _TenantClient(self.client)
        self.assertEqual(self._upload(owner, "email\na@example.com\n").status_code, 422)
        email = f"a-{uuid.uuid4().hex[:6]}@example.com"
        with patch("app.routers.team.deliver", return_value="logged"):
            token = owner.post("/api/team/invitations", json={"email": email, "role": "Agent"}).json()["accept_url"].split("token=")[1]
        access = self.client.post("/api/auth/invitations/accept", json={"token": token, "name": "A", "password": "correct-horse-1"}).json()["access_token"]
        res = self.client.post("/api/crm/leads/import", files={"file": ("l.csv", b"name,phone\nX,+919000000099\n", "text/csv")},
                               headers={"Authorization": f"Bearer {access}"})
        self.assertEqual(res.status_code, 403)

    def test_follow_up_filters_and_counts(self):
        owner = _TenantClient(self.client)
        today = datetime.now(timezone.utc).date()  # the API default tz is UTC
        dates = {"late": today - timedelta(days=2), "now": today, "later": today + timedelta(days=3)}
        ids = {}
        for key, day in dates.items():
            ids[key] = owner.post("/api/crm/leads", json={"name": key, "phone": _phone(), "follow_up_date": day.isoformat()}).json()["id"]
        closed = owner.post("/api/crm/leads", json={"name": "closed", "phone": _phone(), "status": "Converted",
                                                    "follow_up_date": (today - timedelta(days=5)).isoformat()}).json()["id"]
        self.assertEqual(owner.post("/api/crm/leads", json={"name": "bad", "phone": _phone(), "follow_up_date": "next week"}).status_code, 422)
        got = lambda f: [l["id"] for l in owner.get(f"/api/crm/leads?follow_up={f}").json()]  # noqa: E731
        self.assertEqual(got("overdue"), [ids["late"]])
        self.assertEqual(got("today"), [ids["now"]])
        self.assertEqual(got("upcoming"), [ids["later"]])
        self.assertNotIn(closed, got("overdue"))
        follow_ups = owner.get("/api/stats/overview").json()["follow_ups"]
        self.assertEqual(follow_ups, {"overdue": 1, "today": 1})


if __name__ == "__main__":
    unittest.main()
