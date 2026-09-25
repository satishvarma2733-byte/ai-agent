"""Appointments in the application database, shared by the API and the voice worker.

Times are stored as UTC ISO strings ("2026-10-01T09:30:00+00:00") so string comparison orders them
correctly for overlap and availability checks."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.appointment import Appointment


class AppointmentConflict(Exception):
    pass


class AppointmentNotFound(Exception):
    pass


def to_utc_iso(value: str | datetime, tz_name: str | None = "Asia/Kolkata") -> str:
    """Parse an ISO time (a naive one is read in `tz_name`) and return it as a UTC ISO string."""
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(tz_name or "Asia/Kolkata"))
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def as_dict(apt: Appointment) -> dict:
    return {
        "id": apt.id, "title": apt.title, "contact_name": apt.contact_name, "contact_phone": apt.contact_phone,
        "scheduled_start": apt.scheduled_start, "scheduled_end": apt.scheduled_end, "timezone": apt.timezone,
        "status": apt.status, "notes": apt.notes, "source": apt.source,
    }


def find_overlap(db: Session, tenant_id: str, start_utc: str, end_utc: str, exclude_id: str | None = None) -> Appointment | None:
    query = db.query(Appointment).filter(
        Appointment.tenant_id == tenant_id, Appointment.status == "scheduled",
        Appointment.scheduled_start < end_utc, Appointment.scheduled_end > start_utc,
    )
    if exclude_id:
        query = query.filter(Appointment.id != exclude_id)
    return query.first()


def list_scheduled(tenant_id: str, start: str | datetime, end: str | datetime) -> list[dict]:
    """Scheduled appointments overlapping [start, end)."""
    start_utc, end_utc = to_utc_iso(start), to_utc_iso(end)
    db = SessionLocal()
    try:
        rows = db.query(Appointment).filter(
            Appointment.tenant_id == tenant_id, Appointment.status == "scheduled",
            Appointment.scheduled_start < end_utc, Appointment.scheduled_end > start_utc,
        ).order_by(Appointment.scheduled_start).all()
        return [as_dict(r) for r in rows]
    finally:
        db.close()


def book(tenant_id: str, *, contact_name: str, contact_phone: str, start: str | datetime, end: str | datetime,
         tz_name: str = "Asia/Kolkata", notes: str = "", source: str = "voice_agent", title: str = "Appointment") -> dict:
    """Create a scheduled appointment, refusing overlaps (including busy time in connected calendars),
    and queue the appointment_booked workflow event and the calendar update."""
    from app.services import calendar_sync, workflow_events
    start_utc, end_utc = to_utc_iso(start, tz_name), to_utc_iso(end, tz_name)
    db = SessionLocal()
    try:
        if find_overlap(db, tenant_id, start_utc, end_utc) or calendar_sync.busy_conflict(tenant_id, start_utc, end_utc):
            raise AppointmentConflict("That time is already booked. Please choose another slot.")
        apt = Appointment(tenant_id=tenant_id, title=title, contact_name=contact_name, contact_phone=contact_phone,
                          scheduled_start=start_utc, scheduled_end=end_utc, timezone=tz_name, status="scheduled",
                          notes=notes, source=source)
        db.add(apt)
        db.commit()
        db.refresh(apt)
        calendar_sync.mark_changed(db, apt)
        workflow_events.emit(db, tenant_id, "appointment_booked", phone=contact_phone, ref=apt.id)
        if source == "voice_agent":
            from app.services import notifications
            lead = workflow_events.find_lead(db, tenant_id, contact_phone)
            local = datetime.fromisoformat(start_utc).astimezone(ZoneInfo(tz_name or "Asia/Kolkata"))
            notifications.notify(db, tenant_id, [*notifications.managers(db, tenant_id), lead.assigned_user_id if lead else None],
                                 kind="appointment_booked", title=f"The agent booked {contact_name}",
                                 body=local.strftime("%a %d %b, %I:%M %p"), link="/appointments")
        return as_dict(apt)
    finally:
        db.close()


def cancel(tenant_id: str, appointment_id: str, reason: str = "") -> dict:
    from app.services import calendar_sync
    db = SessionLocal()
    try:
        apt = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.tenant_id == tenant_id).first()
        if apt is None:
            raise AppointmentNotFound(f"Appointment {appointment_id} not found.")
        apt.status = "cancelled"
        if reason.strip():
            apt.notes = f"{(apt.notes or '').strip()}\n\nCancellation reason: {reason.strip()}".strip()
        db.commit()
        calendar_sync.mark_changed(db, apt)
        return as_dict(apt)
    finally:
        db.close()
