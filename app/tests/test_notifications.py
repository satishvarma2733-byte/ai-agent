"""In-app notifications."""
import asyncio
import unittest
import uuid
from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.tests.test_consolidation import _TenantClient

PASSWORD = "correct-horse-1"


def _phone() -> str:
    return "+9192" + str(uuid.uuid4().int)[:8]


class TestNotifications(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def _member(self, owner, role, name):
        email = f"n-{uuid.uuid4().hex[:8]}@example.com"
        with patch("app.routers.team.deliver", return_value="logged"):
            token = owner.post("/api/team/invitations", json={"email": email, "role": role}).json()["accept_url"].split("token=")[1]
        access = self.client.post("/api/auth/invitations/accept", json={"token": token, "name": name, "password": PASSWORD}).json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}
        return self.client.get("/api/auth/me", headers=headers).json()["id"], headers

    def _inbox(self, headers):
        return self.client.get("/api/notifications", headers=headers).json()

    def test_assignment_notifies_the_assignee_only(self):
        owner = _TenantClient(self.client)
        agent_id, agent = self._member(owner, "Agent", "Ravi")
        lead = owner.post("/api/crm/leads", json={"name": "Priya", "phone": _phone()}).json()
        owner.put(f"/api/crm/leads/{lead['id']}", json={"assigned_user_id": agent_id})
        inbox = self._inbox(agent)
        self.assertEqual(inbox["unread"], 1)
        self.assertEqual(inbox["items"][0]["kind"], "lead_assigned")
        self.assertIn("Priya", inbox["items"][0]["title"])
        self.assertEqual(owner.get("/api/notifications").json()["unread"], 0)  # assigning isn't news to yourself
        self.assertEqual(self.client.post("/api/notifications/read-all", headers=agent).status_code, 204)
        self.assertEqual(self._inbox(agent)["unread"], 0)
        self.assertEqual(self.client.delete("/api/notifications", headers=agent).status_code, 204)
        self.assertEqual(self._inbox(agent)["items"], [])

    def test_missed_call_notifies_managers_once(self):
        import db_backend
        owner = _TenantClient(self.client)
        _, manager = self._member(owner, "Manager", "Mani")
        _, agent = self._member(owner, "Agent", "Anu")
        room = f"room-{uuid.uuid4().hex[:8]}"
        phone = _phone()
        db_backend.save_call_log(phone, 4, "", call_room_id=room, tenant_id=owner.tenant_id)
        db_backend.save_call_log(phone, 5, "", call_room_id=room, tenant_id=owner.tenant_id)  # later update, same call
        for client_headers in (owner.headers, manager):
            items = self._inbox(client_headers)["items"]
            self.assertEqual([i["kind"] for i in items], ["call_missed"])
        self.assertEqual(self._inbox(agent)["items"], [])

    def test_voice_booking_notifies(self):
        from app.services import appointment_store
        owner = _TenantClient(self.client)
        start = datetime.combine(datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(days=9), time(11, 0), ZoneInfo("Asia/Kolkata"))
        appointment_store.book(owner.tenant_id, contact_name="Kiran", contact_phone=_phone(), start=start, end=start + timedelta(minutes=30))
        item = owner.get("/api/notifications").json()["items"][0]
        self.assertEqual((item["kind"], item["title"]), ("appointment_booked", "The agent booked Kiran"))
        self.assertIn("11:00 AM", item["body"])

    def test_failed_workflow_notifies_managers(self):
        from app.services.workflow_engine import workflow_engine
        owner = _TenantClient(self.client)
        owner.post("/api/crm/workflows", json={"name": "Breaks", "trigger_event": "lead_created", "actions": [{"type": "ai_call", "config": {}}]})
        lead = owner.post("/api/crm/leads", json={"name": "F", "phone": _phone()}).json()
        with patch("app.services.workflow_engine.dispatch_outbound_call", side_effect=RuntimeError("SIP down")):
            asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], owner.tenant_id))
        item = owner.get("/api/notifications").json()["items"][0]
        self.assertEqual((item["kind"], item["title"]), ("workflow_failed", 'Workflow "Breaks" failed'))
        self.assertIn("SIP down", item["body"])

    def test_notifications_are_private(self):
        owner = _TenantClient(self.client)
        agent_id, agent = self._member(owner, "Agent", "Z")
        lead = owner.post("/api/crm/leads", json={"name": "P", "phone": _phone()}).json()
        owner.put(f"/api/crm/leads/{lead['id']}", json={"assigned_user_id": agent_id})
        note_id = self._inbox(agent)["items"][0]["id"]
        self.assertEqual(owner.delete(f"/api/notifications/{note_id}").status_code, 404)
        self.assertEqual(_TenantClient(self.client).delete(f"/api/notifications/{note_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/notifications/{note_id}", headers=agent).status_code, 204)


if __name__ == "__main__":
    unittest.main()
