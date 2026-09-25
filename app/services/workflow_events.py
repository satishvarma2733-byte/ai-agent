"""Workflow trigger queue. Any process can emit; the API's workflow engine claims and runs events."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.workflow import Workflow, WorkflowEvent

logger = logging.getLogger("workflow-events")

MAX_ATTEMPTS = 3
# A claimed event whose run never finished (process crashed) becomes claimable again after this.
# Longer than any run can take, since workflow steps may wait up to an hour each.
CLAIM_TIMEOUT = timedelta(hours=6)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def emit(db: Session, tenant_id: str, event_type: str, *, lead_id: str | None = None,
         phone: str | None = None, ref: str | None = None) -> bool:
    """Queue an event. Skipped when no active workflow listens for it; a repeated `ref` is ignored.
    Commits on its own so callers can emit after their own commit. Returns True when queued."""
    from app.services.workflow_engine import _stored_triggers
    listening = db.query(Workflow.id).filter(
        Workflow.tenant_id == tenant_id, Workflow.is_active == True,
        Workflow.trigger_event.in_(_stored_triggers(event_type)),
    ).first()
    if not listening:
        return False
    db.add(WorkflowEvent(tenant_id=tenant_id, event_type=event_type, lead_id=lead_id, phone=phone,
                         ref=ref, created_at=_now()))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def find_lead(db: Session, tenant_id: str, phone: str | None) -> Lead | None:
    """The lead a phone-addressed event belongs to (phones are stored in E.164)."""
    if not phone:
        return None
    from app.schemas.lead import normalize_phone
    try:
        phone = normalize_phone(phone)
    except ValueError:
        return None
    return db.query(Lead).filter(Lead.tenant_id == tenant_id, Lead.phone == phone, Lead.deleted_at == None).first()


def create_lead_for_caller(db: Session, tenant_id: str, phone: str | None) -> Lead | None:
    """A new lead for an unknown caller (used by the missed-call trigger)."""
    from app.models.lead import LeadActivity
    from app.schemas.lead import normalize_phone
    try:
        phone = normalize_phone(phone or "")
    except ValueError:
        return None
    lead = Lead(tenant_id=tenant_id, name=f"Caller {phone}", phone=phone, status="New", score="Cold",
                notes="Created from a missed call.")
    db.add(lead)
    db.flush()
    db.add(LeadActivity(lead_id=lead.id, tenant_id=tenant_id, activity_type="call", title="Missed call",
                        description="The caller hung up before speaking with the agent."))
    db.commit()
    return lead


def create_lead_for_appointment(db: Session, tenant_id: str, appointment_id: str | None) -> Lead | None:
    """The booked contact as a new lead, so appointment workflows can message them."""
    from app.models.appointment import Appointment
    from app.schemas.lead import normalize_phone
    apt = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.tenant_id == tenant_id).first() if appointment_id else None
    if apt is None:
        return None
    try:
        phone = normalize_phone(apt.contact_phone or "")
    except ValueError:
        return None
    lead = Lead(tenant_id=tenant_id, name=apt.contact_name or f"Caller {phone}", phone=phone, status="New", score="Warm",
                notes="Created from an appointment.")
    db.add(lead)
    db.commit()
    return lead


def claim_batch(db: Session, limit: int = 20) -> list[WorkflowEvent]:
    """Claim unprocessed events. Each claim is a conditional update, so two engines never take the same event."""
    now = _now()
    candidates = db.query(WorkflowEvent.id).filter(
        WorkflowEvent.processed_at.is_(None),
        WorkflowEvent.attempts < MAX_ATTEMPTS,
        (WorkflowEvent.claimed_at.is_(None)) | (WorkflowEvent.claimed_at < now - CLAIM_TIMEOUT),
    ).order_by(WorkflowEvent.created_at).limit(limit).all()
    claimed = []
    for (event_id,) in candidates:
        won = db.query(WorkflowEvent).filter(
            WorkflowEvent.id == event_id, WorkflowEvent.processed_at.is_(None),
            (WorkflowEvent.claimed_at.is_(None)) | (WorkflowEvent.claimed_at < now - CLAIM_TIMEOUT),
        ).update({WorkflowEvent.claimed_at: now, WorkflowEvent.attempts: WorkflowEvent.attempts + 1},
                 synchronize_session=False)
        db.commit()
        if won:
            claimed.append(db.query(WorkflowEvent).filter(WorkflowEvent.id == event_id).first())
    return claimed


def finish(db: Session, event: WorkflowEvent, error: str | None = None) -> None:
    """Mark done, or release for a retry (until MAX_ATTEMPTS) with the error recorded."""
    if error and event.attempts < MAX_ATTEMPTS:
        event.claimed_at = None
    else:
        event.processed_at = _now()
    event.last_error = error
    db.commit()
