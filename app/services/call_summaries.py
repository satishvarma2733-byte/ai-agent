"""Email the business a summary after each call.

Settings live on the workspace (Tenant.call_summaries, JSON). The workflow engine's loop calls send_due(), which
works as an outbox over call_logs: a finished call is emailed once, marked with summary_sent_at. Calls saved by the
voice worker (a separate process) are picked up the same way. Only calls that end after summaries were turned on
are sent, so turning them on never mails out old calls.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.settings import settings
from app.models.call import CallLog
from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger("call-summaries")

CHECK_SECONDS = 30
# The voice worker writes the summary when the call ends; give a late summary this long before sending without it.
SUMMARY_GRACE = timedelta(minutes=2)
MAX_EXTRA_EMAILS = 10
TRANSCRIPT_CHARS = 3000
BATCH = 50


@dataclass
class SummarySettings:
    enabled: bool = False
    to_managers: bool = True
    to_assignee: bool = True
    emails: list[str] = field(default_factory=list)
    min_seconds: int = 15  # shorter calls are usually missed calls, which already notify the team
    include_transcript: bool = False
    timezone: str = "Asia/Kolkata"
    enabled_at: str | None = None


def read_settings(tenant: Tenant) -> SummarySettings:
    try:
        raw = json.loads(tenant.call_summaries or "{}")
    except ValueError:
        raw = {}
    known = {k: v for k, v in raw.items() if k in SummarySettings.__dataclass_fields__}
    return SummarySettings(**known)


def save_settings(db: Session, tenant: Tenant, new: SummarySettings) -> SummarySettings:
    old = read_settings(tenant)
    try:
        ZoneInfo(new.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone '{new.timezone}'.") from exc
    emails = []
    for email in new.emails:
        email = email.strip().lower()
        if email and email not in emails:
            if "@" not in email or " " in email or len(email) > 200:
                raise ValueError(f"'{email}' isn't an email address.")
            emails.append(email)
    if len(emails) > MAX_EXTRA_EMAILS:
        raise ValueError(f"Add at most {MAX_EXTRA_EMAILS} extra addresses.")
    new.emails = emails
    new.min_seconds = max(0, min(int(new.min_seconds), 600))
    # Turning summaries on starts from now; staying on keeps the original start.
    new.enabled_at = (old.enabled_at if old.enabled and old.enabled_at else _now().isoformat()) if new.enabled else None
    tenant.call_summaries = json.dumps(asdict(new))
    db.commit()
    return new


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def recipients(db: Session, tenant_id: str, cfg: SummarySettings, phone: str | None) -> list[str]:
    from app.services import notifications, workflow_events
    user_ids: list[str] = []
    if cfg.to_managers:
        user_ids += notifications.managers(db, tenant_id)
    if cfg.to_assignee and phone:
        lead = workflow_events.find_lead(db, tenant_id, phone)
        if lead and lead.assigned_user_id:
            user_ids.append(lead.assigned_user_id)
    emails = [u.email.lower() for u in db.query(User).filter(User.id.in_(user_ids), User.tenant_id == tenant_id,
                                                              User.status == "active")] if user_ids else []
    return list(dict.fromkeys(emails + cfg.emails))


def _duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds or 0), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def compose(db: Session, log: CallLog, cfg: SummarySettings) -> tuple[str, str]:
    from app.models.agent import Agent
    from app.services import workflow_events
    lead = workflow_events.find_lead(db, log.tenant_id, log.phone_number)
    who = (lead.name if lead else None) or log.caller_name or log.phone_number
    agent = db.get(Agent, log.agent_id) if log.agent_id else None
    tz = ZoneInfo(cfg.timezone)
    ended = (log.updated_at or log.created_at).replace(tzinfo=timezone.utc).astimezone(tz)
    outcome = "booked an appointment" if log.was_booked else "no booking"
    subject = f"{log.direction.title()} call with {who} · {outcome} · {_duration(log.duration_seconds)}"
    lines = [
        f"{log.direction.title()} call with {who} ({log.phone_number})",
        "",
        f"When: {ended.strftime('%a %d %b %Y, %I:%M %p')} ({cfg.timezone})",
        f"Duration: {_duration(log.duration_seconds)}",
        f"Agent: {agent.name if agent else 'default agent'}",
        f"Outcome: {'Appointment booked' if log.was_booked else 'No appointment booked'}",
        f"Caller mood: {log.sentiment or 'unknown'}",
        "",
        "Summary:",
        (log.summary or "").strip() or "No summary was produced for this call.",
    ]
    if cfg.include_transcript and log.transcript:
        text = log.transcript.strip()
        lines += ["", "Transcript:", text[:TRANSCRIPT_CHARS] + (" …(cut; the full transcript is in aVn)" if len(text) > TRANSCRIPT_CHARS else "")]
    lines += ["", f"Open call logs: {settings.frontend_base_url}/call-logs"]
    return subject, "\n".join(lines)


def _ready(log: CallLog, now: datetime) -> bool:
    finished_at = log.updated_at or log.created_at
    return bool((log.summary or "").strip()) or (finished_at is not None and finished_at <= now - SUMMARY_GRACE)


def send_one(db: Session, log: CallLog, cfg: SummarySettings) -> str:
    """Email one call's summary and mark it handled. Returns the recorded status."""
    from app.services.mailer import deliver
    status = "skipped"
    if (log.duration_seconds or 0) >= cfg.min_seconds:
        to = recipients(db, log.tenant_id, cfg, log.phone_number)
        if to:
            subject, body = compose(db, log, cfg)
            outcomes = [deliver(address, subject, body) for address in to]
            status = next((s for s in ("sent", "logged") if s in outcomes), "failed")
    log.summary_sent_at, log.summary_email_status = _now(), status
    db.commit()
    return status


def send_due(now: datetime | None = None) -> int:
    """Send summaries for finished calls in every workspace that has them on. Returns how many were handled."""
    now = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    db = SessionLocal()
    handled = 0
    try:
        tenants = db.query(Tenant).filter(Tenant.call_summaries.isnot(None)).all()
        for tenant in tenants:
            cfg = read_settings(tenant)
            if not cfg.enabled or not cfg.enabled_at:
                continue
            since = datetime.fromisoformat(cfg.enabled_at)
            logs = db.query(CallLog).filter(
                CallLog.tenant_id == tenant.id, CallLog.summary_sent_at.is_(None), CallLog.duration_seconds > 0,
                CallLog.updated_at >= since,
            ).order_by(CallLog.updated_at).limit(BATCH).all()
            for log in logs:
                if not _ready(log, now):
                    continue
                try:
                    send_one(db, log, cfg)
                    handled += 1
                except Exception as exc:
                    db.rollback()
                    logger.error("[SUMMARY] Call %s in %s failed: %s", log.id, tenant.id, exc)
                    # Marked failed so a broken call isn't retried on every pass.
                    db.query(CallLog).filter(CallLog.id == log.id).update({"summary_sent_at": _now(), "summary_email_status": "failed"})
                    db.commit()
        return handled
    finally:
        db.close()
