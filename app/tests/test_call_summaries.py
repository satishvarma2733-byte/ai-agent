"""Emailed call summaries: settings, who receives them, and the send-once outbox over call logs."""
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.call import CallLog
from app.services import call_summaries
from app.services.call_store import record_call_log
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member


def _phone() -> str:
    return "+9195" + str(uuid.uuid4().int)[:8]


class TestCallSummaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        # send_due() covers every workspace; calls other tests left unsent would otherwise be mailed here.
        db = SessionLocal()
        try:
            db.query(CallLog).filter(CallLog.summary_sent_at.is_(None)).update(
                {"summary_sent_at": datetime.now(timezone.utc).replace(tzinfo=None), "summary_email_status": "skipped"})
            db.commit()
        finally:
            db.close()
        self.sent: list[tuple[str, str, str]] = []
        p = patch("app.services.mailer.deliver", side_effect=lambda to, subject, body: self.sent.append((to, subject, body)) or "sent")
        p.start()
        self.addCleanup(p.stop)
        self.owner = _TenantClient(self.client)
        self.owner_email = self.owner.get("/api/auth/me").json()["email"]

    def enable(self, **overrides):
        body = {"enabled": True, "to_managers": True, "to_assignee": True, "emails": [], "min_seconds": 15,
                "include_transcript": False, "timezone": "Asia/Kolkata", **overrides}
        res = self.owner.put("/api/workspace/call-summaries", json=body)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def call(self, phone=None, seconds=125, **fields) -> str:
        room = f"call-{uuid.uuid4().hex[:10]}"
        record_call_log(call_room_id=room, phone=phone or _phone(), tenant_id=self.owner.tenant_id, direction="inbound",
                        duration_seconds=seconds, **fields)
        return room

    def status(self, room: str) -> str | None:
        db = SessionLocal()
        try:
            return db.query(CallLog).filter(CallLog.call_room_id == room).one().summary_email_status
        finally:
            db.close()

    def test_settings_are_validated_and_admin_only(self):
        self.assertFalse(self.owner.get("/api/workspace/call-summaries").json()["enabled"])
        agent = _Member(self.client, self.owner, "Agent")
        self.assertEqual(agent.get("/api/workspace/call-summaries").status_code, 403)
        self.assertEqual(agent.put("/api/workspace/call-summaries", json={"enabled": True}).status_code, 403)
        for bad in ({"emails": ["not-an-email"]}, {"timezone": "Mars/Olympus"}, {"emails": [f"a{i}@x.com" for i in range(11)]}):
            self.assertEqual(self.owner.put("/api/workspace/call-summaries", json={"enabled": True, **bad}).status_code, 422, bad)
        saved = self.enable(emails=[" Front.Desk@Example.com ", "front.desk@example.com"])
        self.assertEqual(saved["emails"], ["front.desk@example.com"])

    def test_each_finished_call_is_emailed_once(self):
        self.enable(emails=["desk@example.com"], include_transcript=True)
        room = self.call(summary="Asked about rooms; booked Friday 4pm.", was_booked=True, sentiment="positive",
                         transcript="Agent: Hello\nCaller: " + "x" * 4000, caller_name="Ravi")
        self.assertEqual(call_summaries.send_due(), 1)
        self.assertEqual(call_summaries.send_due(), 0)
        self.assertEqual(sorted(to for to, _, _ in self.sent), sorted([self.owner_email, "desk@example.com"]))
        _, subject, body = self.sent[0]
        self.assertIn("Inbound call with Ravi · booked an appointment · 2m 05s", subject)
        for part in ("Asked about rooms; booked Friday 4pm.", "Outcome: Appointment booked", "Caller mood: positive",
                     "Transcript:", "(cut; the full transcript is in aVn)", "/call-logs"):
            self.assertIn(part, body)
        self.assertEqual(self.status(room), "sent")

    def test_short_calls_are_skipped(self):
        self.enable()
        room = self.call(seconds=8, summary="hung up")
        call_summaries.send_due()
        self.assertEqual((self.sent, self.status(room)), ([], "skipped"))

    def test_waits_briefly_for_a_late_summary(self):
        self.enable()
        room = self.call()
        self.assertEqual(call_summaries.send_due(), 0)
        later = datetime.now(timezone.utc) + call_summaries.SUMMARY_GRACE + timedelta(seconds=5)
        self.assertEqual(call_summaries.send_due(now=later), 1)
        self.assertIn("No summary was produced for this call.", self.sent[0][2])
        self.assertEqual(self.status(room), "sent")

    def test_old_calls_and_disabled_workspaces_are_not_sent(self):
        before = self.call(summary="before summaries were on")
        self.enable()
        self.call(summary="after")
        self.assertEqual(call_summaries.send_due(), 1)
        self.assertIsNone(self.status(before))
        self.owner.put("/api/workspace/call-summaries", json={"enabled": False})
        self.call(summary="while off")
        self.assertEqual(call_summaries.send_due(), 0)

    def test_assigned_teammate_can_be_the_only_recipient(self):
        member = _Member(self.client, self.owner, "Agent")
        member_id = member.get("/api/auth/me").json()["id"]
        member_email = member.get("/api/auth/me").json()["email"]
        phone = _phone()
        self.owner.post("/api/crm/leads", json={"name": "Asha", "phone": phone, "assigned_user_id": member_id})
        self.enable(to_managers=False)
        self.call(phone=phone, summary="Follow-up call")
        call_summaries.send_due()
        self.assertEqual([to for to, _, _ in self.sent], [member_email])
        self.assertIn("with Asha", self.sent[0][1])

    def test_other_workspaces_calls_never_reach_this_one(self):
        self.enable()
        other = _TenantClient(self.client)
        record_call_log(call_room_id=f"call-{uuid.uuid4().hex[:10]}", phone=_phone(), tenant_id=other.tenant_id,
                        direction="inbound", duration_seconds=90, summary="theirs")
        call_summaries.send_due()
        self.assertEqual(self.sent, [])

    def test_send_a_test_summary(self):
        self.assertEqual(self.owner.post("/api/workspace/call-summaries/test").status_code, 409)
        self.enable()
        room = self.call(summary="Latest call")
        res = self.owner.post("/api/workspace/call-summaries/test")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual((res.json()["recipients"], res.json()["status"]), ([self.owner_email], "sent"))
        self.assertTrue(self.sent[0][1].startswith("[Test] "))
        self.assertIsNone(self.status(room))  # the real summary still goes out


if __name__ == "__main__":
    unittest.main()
