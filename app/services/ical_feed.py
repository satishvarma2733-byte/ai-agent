"""A workspace's appointments as an iCalendar (RFC 5545) feed for Apple Calendar, Outlook and others.

The feed lives at a secret URL (only its hash is stored); anyone with the URL can read the workspace's
appointments, so it is off until an admin turns it on, and rotating it cuts off every old subscriber.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.appointment import Appointment

WINDOW_BEFORE = timedelta(days=30)
WINDOW_AFTER = timedelta(days=365)
PRODID = "-//aVn//Appointments//EN"


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Lines longer than 75 octets continue on the next line, which starts with a space."""
    out, current = [], b""
    for ch in line:
        encoded = ch.encode("utf-8")
        if len(current) + len(encoded) > (75 if not out else 74):
            out.append(current.decode("utf-8"))
            current = b""
        current += encoded
    out.append(current.decode("utf-8"))
    return [out[0]] + [" " + part for part in out[1:]]


def _utc(value: str | datetime) -> str:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def render(db: Session, tenant_id: str, workspace_name: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    start, end = (now - WINDOW_BEFORE).isoformat(), (now + WINDOW_AFTER).isoformat()
    rows = db.query(Appointment).filter(
        Appointment.tenant_id == tenant_id, Appointment.status.in_(("scheduled", "cancelled", "completed")),
        Appointment.scheduled_start >= start, Appointment.scheduled_start <= end,
    ).order_by(Appointment.scheduled_start).all()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_escape(f'{workspace_name} appointments')}", "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
             "X-PUBLISHED-TTL:PT15M"]
    stamp = _utc(now)
    for apt in rows:
        summary = f"{apt.title}: {apt.contact_name}" if apt.title and apt.title != apt.contact_name else apt.contact_name
        description = f"Phone: {apt.contact_phone}" + (f"\n\n{apt.notes.strip()}" if apt.notes else "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{apt.id}@avn",
            f"DTSTAMP:{stamp}",
            f"LAST-MODIFIED:{_utc(apt.updated_at or apt.created_at)}",
            f"DTSTART:{_utc(apt.scheduled_start)}",
            f"DTEND:{_utc(apt.scheduled_end)}",
            f"SUMMARY:{_escape(summary)}",
            f"DESCRIPTION:{_escape(description)}",
            f"STATUS:{'CANCELLED' if apt.status == 'cancelled' else 'CONFIRMED'}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in lines for folded in _fold(line)) + "\r\n"
