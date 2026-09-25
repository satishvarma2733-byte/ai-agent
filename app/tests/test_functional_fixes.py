"""Functional bugs from the 2026-09-25 audit (BUG-06, 07, 09, 10, 11, 14, 15, 16)."""
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.call import CallLog
from app.tests.test_consolidation import _TenantClient


def _phone() -> str:
    return "+9198" + str(uuid.uuid4().int)[:8]


class TestFunctionalFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def test_lead_phone_status_and_duplicates(self):
        owner = _TenantClient(self.client)
        self.assertEqual(owner.post("/api/crm/leads", json={"name": "A", "phone": "abc"}).status_code, 422)
        self.assertEqual(owner.post("/api/crm/leads", json={"name": "A", "phone": _phone(), "status": "Whatever"}).status_code, 422)
        phone = _phone()
        created = owner.post("/api/crm/leads", json={"name": "A", "phone": f"{phone[:6]} {phone[6:]}"})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["phone"], phone)
        self.assertEqual(owner.post("/api/crm/leads", json={"name": "B", "phone": phone}).status_code, 409)
        # Another workspace may hold the same number.
        self.assertEqual(_TenantClient(self.client).post("/api/crm/leads", json={"name": "C", "phone": phone}).status_code, 201)

    def test_timestamps_carry_utc_offset(self):
        owner = _TenantClient(self.client)
        created = owner.post("/api/crm/leads", json={"name": "T", "phone": _phone()}).json()
        stamp = datetime.fromisoformat(created["created_at"].replace("Z", "+00:00"))
        self.assertIsNotNone(stamp.tzinfo)
        self.assertLess(abs(datetime.now(timezone.utc) - stamp), timedelta(minutes=1))

    def test_lead_list_pages_and_searches(self):
        owner = _TenantClient(self.client)
        for name in ("Asha", "Bala", "Chitra"):
            owner.post("/api/crm/leads", json={"name": name, "phone": _phone()})
        self.assertEqual(len(owner.get("/api/crm/leads?limit=2").json()), 2)
        self.assertEqual([l["name"] for l in owner.get("/api/crm/leads?search=bal").json()], ["Bala"])

    def test_appointment_window_and_source(self):
        owner = _TenantClient(self.client)
        start = datetime.now(timezone.utc) + timedelta(days=3)
        body = {"contact_name": "P", "contact_phone": "+919000000001", "timezone": "UTC",
                "scheduled_start": start.strftime("%Y-%m-%dT%H:%M"),
                "scheduled_end": (start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")}
        backwards = dict(body, scheduled_end=(start - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"))
        self.assertEqual(owner.post("/api/appointments", json=backwards).status_code, 422)
        past = dict(body, scheduled_start="2020-01-01T10:00", scheduled_end="2020-01-01T10:30")
        self.assertEqual(owner.post("/api/appointments", json=past).status_code, 422)
        created = owner.post("/api/appointments", json=body)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["source"], "manual_ui")
        # Changing only the status of a booking is always allowed.
        self.assertEqual(owner.patch(f"/api/appointments/{created.json()['id']}", json={"status": "completed"}).status_code, 200)

    def test_whatsapp_does_not_claim_success(self):
        res = _TenantClient(self.client).post("/api/crm/whatsapp", json={"phone": "+919000000001", "text": "x"})
        self.assertEqual(res.status_code, 501)
        self.assertIn("No message was sent", res.json()["detail"])

    def test_call_control_targets_own_calls(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        room = f"room-{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=owner.tenant_id, phone_number="+919000000040", call_room_id=room, direction="inbound"))
            db.commit()
        finally:
            db.close()
        self.assertEqual(owner.post("/api/inbound/end", json={"id": "no-such-room"}).status_code, 404)
        self.assertEqual(other.post("/api/inbound/end", json={"id": room}).status_code, 404)
        with patch("app.services.call_control.end_call", AsyncMock()) as end:
            self.assertEqual(owner.post("/api/inbound/end", json={"id": room}).status_code, 200)
        self.assertEqual(end.await_args.args[0].call_room_id, room)
        for path in ("/api/inbound/transfer", "/api/outbound/voicemail", "/api/inbound/start"):
            self.assertEqual(owner.post(path, json={"id": room}).status_code, 501, path)

    def test_overview_uses_only_this_workspace(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        empty = owner.get("/api/stats/overview?tz=Asia/Kolkata").json()
        self.assertEqual(empty["totals"]["calls"], 0)
        self.assertEqual(empty["latency"]["turns"], 0)
        self.assertIsNone(empty["latency"]["avg_total_ms"])
        self.assertEqual(len(empty["daily"]), 14)
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=owner.tenant_id, phone_number="+919000000050", call_room_id=f"r-{uuid.uuid4().hex[:8]}",
                           direction="inbound", duration_seconds=120, was_booked=True, sentiment="positive", estimated_cost_usd=0.5))
            db.add(CallLog(tenant_id=other.tenant_id, phone_number="+919000000051", direction="inbound"))
            db.commit()
        finally:
            db.close()
        data = owner.get("/api/stats/overview?tz=Asia/Kolkata").json()
        self.assertEqual(data["totals"]["calls"], 1)
        self.assertEqual(data["totals"]["calls_today"], 1)
        self.assertEqual(data["totals"]["booking_rate"], 100)
        self.assertEqual(data["totals"]["minutes"], 2)
        self.assertEqual(data["trend"]["calls_7d"], 1)
        self.assertEqual(data["daily"][-1]["calls"], 1)
        self.assertEqual(data["daily"][-1]["avg_duration"], 120)
        self.assertEqual(data["sentiment"], {"positive": 1})
        self.assertEqual(data["month"]["cost_usd"], 0.5)
        self.assertEqual(data["activity"][0]["kind"], "call")
        self.assertEqual(len(owner.get("/api/stats/overview?days=90").json()["daily"]), 90)
        self.assertEqual(owner.get("/api/stats/overview?tz=Mars/Base").status_code, 422)

    def test_live_calls_come_from_livekit(self):
        owner = _TenantClient(self.client)
        with patch("app.core.runtime_config.load_runtime_config", return_value={}), \
             patch("app.services.call_control.get_livekit_settings", return_value={"url": "", "api_key": "", "api_secret": ""}):
            self.assertEqual(owner.get("/api/calls/live").json(), {"configured": False, "calls": []})

        room = f"room-{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=owner.tenant_id, phone_number="+919000000060", call_room_id=room, direction="outbound"))
            db.commit()
        finally:
            db.close()

        class Room:
            def __init__(self, name, participants):
                self.name, self.num_participants, self.creation_time = name, participants, 1790000000

        lk = AsyncMock()
        lk.room.list_rooms.return_value.rooms = [Room(room, 2), Room("someone-elses-room", 2)]
        with patch("app.core.runtime_config.load_runtime_config", return_value={}), \
             patch("app.services.call_control._client", return_value=lk):
            live = owner.get("/api/calls/live").json()
        self.assertTrue(live["configured"])
        self.assertEqual([c["room"] for c in live["calls"]], [room])
        self.assertIn(room, lk.room.list_rooms.await_args.args[0].names)

    def test_sessions_list_and_revoke(self):
        owner = _TenantClient(self.client)
        me = owner.get("/api/auth/me").json()
        second = self.client.post("/api/auth/login", json={"email": me["email"], "password": "correct-horse-1"}).json()["access_token"]
        sessions = owner.get("/api/auth/sessions").json()
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sum(s["current"] for s in sessions), 1)
        other_device = next(s for s in sessions if not s["current"])
        self.assertEqual(_TenantClient(self.client).delete(f"/api/auth/sessions/{other_device['id']}").status_code, 404)
        self.assertEqual(owner.delete(f"/api/auth/sessions/{other_device['id']}").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {second}"}).status_code, 401)
        self.assertEqual(len(owner.get("/api/auth/sessions").json()), 1)

    def test_workspace_rename_is_admin_only(self):
        owner = _TenantClient(self.client)
        self.assertEqual(owner.get("/api/workspace").json()["name"], "Co")
        renamed = owner.patch("/api/workspace", json={"name": "  Acme Clinics "})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["name"], "Acme Clinics")
        self.assertEqual(owner.patch("/api/workspace", json={"name": "   "}).status_code, 422)
        email = f"ws-{uuid.uuid4().hex[:6]}@example.com"
        with patch("app.routers.team.deliver", return_value="logged"):
            token = owner.post("/api/team/invitations", json={"email": email, "role": "Manager"}).json()["accept_url"].split("token=")[1]
        access = self.client.post("/api/auth/invitations/accept", json={"token": token, "name": "M", "password": "correct-horse-1"}).json()["access_token"]
        res = self.client.patch("/api/workspace", json={"name": "Nope"}, headers={"Authorization": f"Bearer {access}"})
        self.assertEqual(res.status_code, 403)

    def test_workflow_triggers_and_run_history(self):
        import asyncio
        from app.services.workflow_engine import workflow_engine

        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        self.assertEqual(owner.post("/api/crm/workflows", json={"name": "x", "trigger_event": "missed_call", "actions": []}).status_code, 422)
        # Lead first, so its creation doesn't queue an event for this workflow (the engine is run directly below).
        lead = owner.post("/api/crm/leads", json={"name": "W", "phone": _phone()}).json()
        created = owner.post("/api/crm/workflows", json={"name": "Welcome", "trigger_event": "new_lead", "actions": [
            {"type": "create_reminder", "config": {"text": "Call back"}},
            {"type": "send_whatsapp", "config": {}},
            {"type": "update_crm", "config": {"field": "tenant_id", "value": "x"}},
            {"type": "visual_layout", "config": {"nodes": []}},
        ]})
        self.assertEqual(created.status_code, 201, created.text)
        wf = created.json()
        self.assertEqual(wf["trigger_event"], "lead_created")

        asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], owner.tenant_id))
        runs = owner.get(f"/api/crm/workflows/{wf['id']}/runs").json()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "success")
        self.assertIn("reminder added", runs[0]["message"])
        self.assertIn("WhatsApp skipped: no message or template configured", runs[0]["message"])
        self.assertIn("not allowed", runs[0]["message"])
        self.assertEqual(other.get(f"/api/crm/workflows/{wf['id']}/runs").status_code, 404)
        # Another tenant's lead id never runs this tenant's workflows.
        asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], other.tenant_id))
        self.assertEqual(len(owner.get(f"/api/crm/workflows/{wf['id']}/runs").json()), 1)

    def test_system_status_reports_what_calls_need(self):
        owner = _TenantClient(self.client)
        empty = {"url": "", "api_key": "", "api_secret": ""}
        full = {"url": "wss://x", "api_key": "k", "api_secret": "s"}
        with patch("app.routers.system.load_runtime_config", return_value={"google_api_key": ""}), \
             patch("outbound_calls.get_livekit_settings", return_value=empty), patch.dict("os.environ", {"GOOGLE_API_KEY": ""}):
            status = owner.get("/api/system/status").json()
        self.assertFalse(status["ready"])
        self.assertEqual(status["missing"], ["LiveKit", "AI model key"])
        self.assertIsNone(status["last_call_at"])
        with patch("app.routers.system.load_runtime_config", return_value={"google_api_key": "g"}), \
             patch("outbound_calls.get_livekit_settings", return_value=full):
            self.assertTrue(owner.get("/api/system/status").json()["ready"])

    def test_cms_prompt_delete(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        prompt = owner.post("/api/cms/agent-prompts", json={"name": "Greeting", "content": "Hello"})
        self.assertEqual(prompt.status_code, 201, prompt.text)
        pid = prompt.json()["id"]
        self.assertEqual(other.delete(f"/api/cms/agent-prompts/{pid}").status_code, 404)
        self.assertEqual(owner.delete(f"/api/cms/agent-prompts/{pid}").status_code, 200)
        self.assertEqual(owner.delete(f"/api/cms/agent-prompts/{pid}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
