"""Workflows that run a set time before an appointment, and {{appointment.*}} placeholders."""
import asyncio
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.lead import Lead, LeadActivity
from app.models.workflow import WorkflowEvent
from app.services import appointment_reminders
from app.services.placeholders import render
from app.services.workflow_engine import workflow_engine
from app.tests.test_consolidation import _TenantClient


def _phone() -> str:
    return "+9196" + str(uuid.uuid4().int)[:8]


class TestAppointmentReminders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def workflow(self, owner, minutes_before=None, subject="Reminder for {{appointment.time}}", trigger="appointment_reminder"):
        body = {"name": f"R{minutes_before}", "trigger_event": trigger,
                "actions": [{"type": "send_email", "config": {"subject": subject, "body": "See you, {{lead.first_name}}"}}]}
        if minutes_before is not None:
            body["trigger_config"] = {"minutes_before": minutes_before}
        res = owner.post("/api/crm/workflows", json=body)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def book(self, owner, hours_ahead: float, phone: str | None = None) -> dict:
        start = (datetime.now(timezone.utc) + timedelta(hours=hours_ahead)).replace(second=0, microsecond=0)
        res = owner.post("/api/appointments", json={
            "contact_name": "Meera Iyer", "contact_phone": phone or _phone(), "timezone": "Asia/Kolkata",
            "scheduled_start": start.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%dT%H:%M"),
            "scheduled_end": (start + timedelta(minutes=30)).astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%dT%H:%M")})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def queued(self, tenant_id: str) -> list[WorkflowEvent]:
        db = SessionLocal()
        try:
            return db.query(WorkflowEvent).filter(WorkflowEvent.tenant_id == tenant_id,
                                                  WorkflowEvent.event_type == "appointment_reminder").all()
        finally:
            db.close()

    def run_event(self, event: WorkflowEvent) -> None:
        asyncio.run(workflow_engine._run_event(event.id, event.tenant_id, event.event_type, event.lead_id, event.phone, event.ref))

    def test_lead_time_is_validated(self):
        owner = _TenantClient(self.client)
        self.assertEqual(self.workflow(owner)["trigger_config"], {"minutes_before": 1440})
        self.assertEqual(self.workflow(owner, 120)["trigger_config"], {"minutes_before": 120})
        for bad in (5, 20000, "soon"):
            res = owner.post("/api/crm/workflows", json={"name": "x", "trigger_event": "appointment_reminder",
                                                        "trigger_config": {"minutes_before": bad}, "actions": []})
            self.assertEqual(res.status_code, 422, bad)
        # Other triggers ignore settings.
        self.assertIsNone(self.workflow(owner, 60, trigger="lead_created")["trigger_config"])

    def test_due_appointments_are_queued_once_per_workflow(self):
        owner = _TenantClient(self.client)
        day = self.workflow(owner, 1440)
        self.workflow(owner, 120)         # not due for any of these
        soon = self.book(owner, 20)       # inside the day window only
        self.book(owner, 30)              # not yet due
        self.book(owner, 0.05)            # starts in 3 minutes: too late to remind
        cancelled = self.book(owner, 10)
        owner.post(f"/api/appointments/{cancelled['id']}/cancel", json={})
        appointment_reminders.queue_due()
        appointment_reminders.queue_due()
        refs = [appointment_reminders.parse_ref(e.ref) for e in self.queued(owner.tenant_id)]
        self.assertEqual([(r[0], r[1]) for r in refs], [(soon["id"], day["id"])])

    def test_reminder_runs_only_its_workflow_with_appointment_details(self):
        owner = _TenantClient(self.client)
        phone = _phone()
        lead = owner.post("/api/crm/leads", json={"name": "Meera Iyer", "phone": phone, "email": "meera@example.com"}).json()
        day, two_hours = self.workflow(owner, 1440), self.workflow(owner, 120)
        apt = self.book(owner, 20, phone)
        appointment_reminders.queue_due()
        [event] = self.queued(owner.tenant_id)
        self.run_event(event)
        self.assertEqual(len(owner.get(f"/api/crm/workflows/{day['id']}/runs").json()), 1)
        self.assertEqual(owner.get(f"/api/crm/workflows/{two_hours['id']}/runs").json(), [])
        local = datetime.fromisoformat(apt["scheduled_start"]).astimezone(timezone(timedelta(hours=5, minutes=30)))
        db = SessionLocal()
        try:
            notes = [a.description for a in db.query(LeadActivity).filter(LeadActivity.lead_id == lead["id"],
                                                                         LeadActivity.title == "Workflow email")]
        finally:
            db.close()
        self.assertEqual(len(notes), 1)
        self.assertIn(f"Reminder for {local.strftime('%a %d %b, %I:%M %p')}", notes[0])

    def test_moved_or_cancelled_appointments_are_not_reminded_for_the_old_time(self):
        owner = _TenantClient(self.client)
        wf = self.workflow(owner, 1440)
        apt = self.book(owner, 20)
        appointment_reminders.queue_due()
        [old] = self.queued(owner.tenant_id)
        later = datetime.fromisoformat(apt["scheduled_start"]) + timedelta(hours=2)
        ist = timezone(timedelta(hours=5, minutes=30))
        self.assertEqual(owner.patch(f"/api/appointments/{apt['id']}", json={
            "scheduled_start": later.astimezone(ist).strftime("%Y-%m-%dT%H:%M"),
            "scheduled_end": (later + timedelta(minutes=30)).astimezone(ist).strftime("%Y-%m-%dT%H:%M")}).status_code, 200)
        self.run_event(old)
        self.assertEqual(owner.get(f"/api/crm/workflows/{wf['id']}/runs").json(), [])
        appointment_reminders.queue_due()
        self.assertEqual(len(self.queued(owner.tenant_id)), 2)  # the new time gets its own reminder

    def test_booked_contact_becomes_a_lead(self):
        owner = _TenantClient(self.client)
        self.workflow(owner, trigger="appointment_booked", subject="Booked for {{appointment.date}}")
        phone = _phone()
        apt = self.book(owner, 48, phone)
        db = SessionLocal()
        try:
            [event] = db.query(WorkflowEvent).filter(WorkflowEvent.tenant_id == owner.tenant_id,
                                                     WorkflowEvent.event_type == "appointment_booked").all()
        finally:
            db.close()
        asyncio.run(workflow_engine._run_event(event.id, event.tenant_id, event.event_type, event.lead_id, event.phone, event.ref))
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(Lead.tenant_id == owner.tenant_id, Lead.phone == phone).one()
        finally:
            db.close()
        self.assertEqual(lead.name, "Meera Iyer")
        self.assertEqual(apt["contact_phone"], phone)

    def test_placeholders(self):
        lead = SimpleNamespace(name="Meera Iyer", phone="+91", email=None, company=None, status="New", score="Warm",
                               assigned_agent=None, follow_up_date=None, custom_fields={"city": "Pune"})
        apt = SimpleNamespace(title="Consultation", scheduled_start="2026-10-05T04:30:00+00:00", timezone="Asia/Kolkata")
        text = "{{lead.first_name}} in {{custom.city}}: {{appointment.title}} {{appointment.time}} / {{appointment.start_time}} @ {{workspace.name}} {{lead.nope}}"
        self.assertEqual(render(text, lead, "Clinic", apt), "Meera in Pune: Consultation Mon 05 Oct, 10:00 AM / 10:00 AM @ Clinic ")


if __name__ == "__main__":
    unittest.main()
