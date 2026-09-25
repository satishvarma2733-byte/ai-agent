"""Persistence used by the voice worker, so calls land in the same database the API reads."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.database import SessionLocal
from app.core.settings import settings
from app.models.call import CallLog
from app.models.campaign import CampaignLead
from app.models.tenant import Tenant

logger = logging.getLogger("call-store")

# An inbound caller who hangs up this quickly never really spoke with the agent: treat it as missed.
MISSED_CALL_SECONDS = 15


def resolve_tenant_id(job_meta: dict[str, Any] | None = None) -> str | None:
    """Tenant for a call: dispatch metadata first (outbound/campaigns), then DEFAULT_TENANT_ID,
    then the only tenant if exactly one exists. Inbound numbers are not yet mapped per tenant."""
    tenant_id = str((job_meta or {}).get("tenant_id") or "").strip()
    if tenant_id:
        return tenant_id
    tenant_id = settings.default_tenant_id.strip()
    if tenant_id:
        return tenant_id
    db = SessionLocal()
    try:
        tenants = db.query(Tenant.id).limit(2).all()
        if len(tenants) == 1:
            return tenants[0][0]
    finally:
        db.close()
    logger.warning("[CallStore] Could not resolve tenant for call; set DEFAULT_TENANT_ID.")
    return None


def record_call_log(
    *,
    call_room_id: str,
    phone: str,
    tenant_id: str | None,
    direction: str,
    agent_id: str | None = None,
    **fields: Any,
) -> None:
    """Create or update the call log for a room. Calls whose tenant can't be determined are not stored:
    every row must belong to a tenant (set DEFAULT_TENANT_ID when several tenants share inbound numbers)."""
    db = SessionLocal()
    try:
        log = None
        if call_room_id:
            log = db.query(CallLog).filter(CallLog.call_room_id == call_room_id).first()
        if not log:
            if not tenant_id:
                logger.error(f"[CallStore] Dropping call log for room {call_room_id}: no tenant. Set DEFAULT_TENANT_ID.")
                return
            log = CallLog(call_room_id=call_room_id, phone_number=phone)
            db.add(log)
        previous_duration = log.duration_seconds or 0
        log.phone_number = phone
        log.direction = direction
        if tenant_id:
            log.tenant_id = tenant_id
        if agent_id:
            log.agent_id = agent_id
        for key, value in fields.items():
            if value is not None and hasattr(CallLog, key):
                setattr(log, key, value)
        db.commit()
        # A saved duration means the call has ended; the room makes the event fire once per call.
        if log.tenant_id and (log.duration_seconds or 0) > 0 and call_room_id:
            from app.services import workflow_events
            events = ["call_completed"]
            if log.direction == "inbound" and log.duration_seconds < MISSED_CALL_SECONDS:
                events.append("call_missed")
                if not previous_duration:  # first save of the finished call
                    _notify_missed(db, log)
            for event in events:
                try:
                    workflow_events.emit(db, log.tenant_id, event, phone=log.phone_number, ref=call_room_id)
                except Exception as exc:
                    logger.error(f"[CallStore] Could not queue {event} for room {call_room_id}: {exc}")
    finally:
        db.close()


def _notify_missed(db, log: CallLog) -> None:
    from app.services import notifications, workflow_events
    lead = workflow_events.find_lead(db, log.tenant_id, log.phone_number)
    who = lead.name if lead else log.phone_number
    notifications.notify(db, log.tenant_id, [*notifications.managers(db, log.tenant_id), lead.assigned_user_id if lead else None],
                         kind="call_missed", title=f"Missed call from {who}",
                         body=f"{log.phone_number} hung up after {log.duration_seconds}s.", link="/call-logs")


def finish_campaign_lead(campaign_lead_id: str, outcome: str) -> None:
    db = SessionLocal()
    try:
        lead = db.query(CampaignLead).filter(CampaignLead.id == campaign_lead_id).first()
        if not lead:
            logger.warning(f"[CallStore] Campaign lead {campaign_lead_id} not found.")
            return
        lead.status = "completed"
        lead.outcome = outcome
        lead.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
