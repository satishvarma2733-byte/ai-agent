"""Queues "appointment_reminder" workflow events when a scheduled appointment comes within a workflow's lead time.

Each (appointment, workflow, start time) is queued once: the event's `ref` makes it unique, and moving the
appointment gives it a new start time, so the moved appointment is reminded again.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.models.appointment import Appointment
from app.models.workflow import Workflow, WorkflowEvent

logger = logging.getLogger("appointment-reminders")

DEFAULT_REMINDER_MINUTES = 1440
MIN_REMINDER_MINUTES = 15
MAX_REMINDER_MINUTES = 7 * 1440
# Too close to the start, a reminder is noise.
LAST_CALL = timedelta(minutes=5)
CHECK_SECONDS = 60


def reminder_ref(appointment_id: str, workflow_id: str, start: str) -> str:
    return f"{appointment_id}|{workflow_id}|{start}"


def parse_ref(ref: str | None) -> tuple[str, str, str] | None:
    parts = (ref or "").split("|")
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else None


def minutes_before(wf: Workflow) -> int:
    try:
        return int(json.loads(wf.trigger_config or "{}").get("minutes_before", DEFAULT_REMINDER_MINUTES))
    except (ValueError, TypeError):
        return DEFAULT_REMINDER_MINUTES


def queue_due(now: datetime | None = None) -> int:
    """Queue reminders that are due now for every workspace. Returns how many were queued."""
    now = now or datetime.now(timezone.utc)
    db = SessionLocal()
    queued = 0
    try:
        workflows = db.query(Workflow).filter(Workflow.trigger_event == "appointment_reminder", Workflow.is_active == True).all()  # noqa: E712
        for wf in workflows:
            lead_time = timedelta(minutes=minutes_before(wf))
            # Due when the start is within the lead time and not about to begin.
            due = db.query(Appointment).filter(
                Appointment.tenant_id == wf.tenant_id, Appointment.status == "scheduled",
                Appointment.scheduled_start > (now + LAST_CALL).isoformat(),
                Appointment.scheduled_start <= (now + lead_time).isoformat(),
            ).all()
            for apt in due:
                ref = reminder_ref(apt.id, wf.id, apt.scheduled_start)
                if db.query(WorkflowEvent.id).filter(WorkflowEvent.tenant_id == wf.tenant_id,
                                                     WorkflowEvent.event_type == "appointment_reminder",
                                                     WorkflowEvent.ref == ref).first():
                    continue
                db.add(WorkflowEvent(tenant_id=wf.tenant_id, event_type="appointment_reminder", phone=apt.contact_phone,
                                     ref=ref, created_at=now.replace(tzinfo=None)))
                try:
                    db.commit()
                    queued += 1
                except Exception:  # another engine queued it first (unique ref)
                    db.rollback()
        return queued
    finally:
        db.close()
