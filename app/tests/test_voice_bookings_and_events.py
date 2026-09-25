"""Voice-agent bookings land in the app database; workflow events flow through the durable queue."""
import asyncio
import unittest
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.appointment import Appointment
from app.models.workflow import WorkflowEvent
from app.services.workflow_engine import workflow_engine
from app.tests.test_consolidation import _TenantClient

IST = ZoneInfo("Asia/Kolkata")


def _next_monday() -> date:
    today = datetime.now(IST).date()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _phone() -> str:
    return "+9197" + str(uuid.uuid4().int)[:8]


def _drain() -> int:
    """Claim queued events and wait for their runs to finish."""
    async def run():
        # The shared test database may hold events from other tests; keep claiming until the queue is empty.
        total = 0
        while n := await workflow_engine.poll_once():
            total += n
            await asyncio.gather(*list(workflow_engine.running))
        return total
    return asyncio.run(run())


def _workflow(client, trigger: str, text: str) -> str:
    res = client.post("/api/crm/workflows", json={"name": f"On {trigger}", "trigger_event": trigger,
                                                   "actions": [{"type": "create_reminder", "config": {"text": text}}]})
    assert res.status_code == 201, res.text
    return res.json()["id"]


class TestVoiceBookingsAndEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def test_voice_agent_books_into_app_database(self):
        import calendar_tools
        owner = _TenantClient(self.client)
        slot = datetime.combine(_next_monday(), time(11, 0), IST)
        booked = asyncio.run(calendar_tools.async_create_booking(slot.isoformat(), "Caller", "+919000000070", tenant_id=owner.tenant_id))
        self.assertTrue(booked["success"], booked)
        again = asyncio.run(calendar_tools.async_create_booking(slot.isoformat(), "Other", "+919000000071", tenant_id=owner.tenant_id))
        self.assertFalse(again["success"])
        db = SessionLocal()
        try:
            apt = db.query(Appointment).filter(Appointment.id == booked["booking_id"]).one()
            self.assertEqual((apt.tenant_id, apt.source), (owner.tenant_id, "voice_agent"))
            self.assertEqual(apt.scheduled_start, slot.astimezone(ZoneInfo("UTC")).isoformat())
        finally:
            db.close()
        slots = asyncio.run(calendar_tools.get_available_slots(_next_monday().isoformat(), tenant_id=owner.tenant_id))
        self.assertNotIn(slot.isoformat(), [s["start_time"] for s in slots])
        self.assertIn(slot.replace(hour=12).isoformat(), [s["start_time"] for s in slots])
        # Another workspace's calendar is unaffected.
        other = _TenantClient(self.client)
        other_slots = asyncio.run(calendar_tools.get_available_slots(_next_monday().isoformat(), tenant_id=other.tenant_id))
        self.assertIn(slot.isoformat(), [s["start_time"] for s in other_slots])
        # The dashboard sees it and refuses an overlapping manual booking.
        self.assertIn(booked["booking_id"], [a["id"] for a in owner.get("/api/appointments").json()])
        clash = owner.post("/api/appointments", json={"contact_name": "M", "contact_phone": "+919000000072", "timezone": "Asia/Kolkata",
                                                      "scheduled_start": slot.strftime("%Y-%m-%dT%H:%M"),
                                                      "scheduled_end": (slot + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")})
        self.assertEqual(clash.status_code, 409, clash.text)
        self.assertTrue(calendar_tools.cancel_booking(booked["booking_id"], tenant_id=owner.tenant_id)["success"])
        self.assertFalse(calendar_tools.cancel_booking(booked["booking_id"], tenant_id=other.tenant_id)["success"])

    def test_booking_by_voice_agent_fires_workflow(self):
        from app.services import appointment_store
        owner = _TenantClient(self.client)
        phone = _phone()
        wf = _workflow(owner, "appointment_booked", "Prepare for the appointment")
        owner.post("/api/crm/leads", json={"name": "Booker", "phone": phone})
        slot = datetime.combine(_next_monday(), time(15, 0), IST)
        appointment_store.book(owner.tenant_id, contact_name="Booker", contact_phone=phone.replace("+91", "+91 "),
                               start=slot, end=slot + timedelta(minutes=30))
        self.assertGreaterEqual(_drain(), 1)
        runs = owner.get(f"/api/crm/workflows/{wf}/runs").json()
        self.assertEqual(len(runs), 1)
        self.assertIn("reminder added", runs[0]["message"])

    def test_call_completed_fires_once_per_call(self):
        import db_backend
        owner = _TenantClient(self.client)
        phone = _phone()
        wf = _workflow(owner, "call_completed", "Review the call")
        owner.post("/api/crm/leads", json={"name": "Caller", "phone": phone})
        room = f"room-{uuid.uuid4().hex[:8]}"
        db_backend.save_call_log(phone, 0, "", call_room_id=room, tenant_id=owner.tenant_id)  # call still running
        db_backend.save_call_log(phone, 95, "hello", call_room_id=room, tenant_id=owner.tenant_id)
        db_backend.save_call_log(phone, 96, "hello", call_room_id=room, tenant_id=owner.tenant_id)  # a later update
        _drain()
        self.assertEqual(len(owner.get(f"/api/crm/workflows/{wf}/runs").json()), 1)
        db = SessionLocal()
        try:
            events = db.query(WorkflowEvent).filter(WorkflowEvent.tenant_id == owner.tenant_id).all()
            self.assertEqual(len(events), 1)
            self.assertIsNotNone(events[0].processed_at)
        finally:
            db.close()

    def test_missed_call_creates_the_lead_and_fires(self):
        import db_backend
        owner = _TenantClient(self.client)
        wf = _workflow(owner, "call_missed", "Call them back")
        unknown = _phone()
        db_backend.save_call_log(unknown, 6, "", call_room_id=f"room-{uuid.uuid4().hex[:8]}", tenant_id=owner.tenant_id)
        # A real conversation isn't a missed call, and neither is an outbound call.
        db_backend.save_call_log(_phone(), 240, "hi", call_room_id=f"room-{uuid.uuid4().hex[:8]}", tenant_id=owner.tenant_id)
        db_backend.save_call_log(_phone(), 5, "", call_room_id=f"room-{uuid.uuid4().hex[:8]}", tenant_id=owner.tenant_id, direction="outbound")
        _drain()
        self.assertEqual(len(owner.get(f"/api/crm/workflows/{wf}/runs").json()), 1)
        leads = [l for l in owner.get("/api/crm/leads").json() if l["phone"] == unknown]
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["name"], f"Caller {unknown}")

    def test_events_are_not_queued_without_a_listening_workflow(self):
        owner = _TenantClient(self.client)
        owner.post("/api/crm/leads", json={"name": "Quiet", "phone": _phone()})
        db = SessionLocal()
        try:
            self.assertEqual(db.query(WorkflowEvent).filter(WorkflowEvent.tenant_id == owner.tenant_id).count(), 0)
        finally:
            db.close()

    def test_lead_created_goes_through_queue(self):
        owner = _TenantClient(self.client)
        wf = _workflow(owner, "lead_created", "Welcome call")
        owner.post("/api/crm/leads", json={"name": "Queued", "phone": _phone()})
        self.assertGreaterEqual(_drain(), 1)
        self.assertEqual(len(owner.get(f"/api/crm/workflows/{wf}/runs").json()), 1)


if __name__ == "__main__":
    unittest.main()
