"""What each workspace's plan allows, and enforcing it.

Limits come from the plans file (a plan's "limits": minutes_per_month, agents, members; the "free" entry covers
workspaces without a paid plan). A plan without limits, or no plans file, means unlimited.

At the minutes limit, new outbound calls, bulk dials, campaign starts and workflow calls are refused and running
campaigns pause. Inbound calls are still answered: a business shouldn't miss its customers because of billing.
Owners and Admins get a notification and an email at 80% and at 100%, once each per month.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.settings import settings
from app.models.agent import Agent
from app.models.auth import Invitation
from app.models.call import CallLog
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.models.user import User
from app.services import billing

logger = logging.getLogger("plan-limits")

WARN_AT = 0.8
CHECK_SECONDS = 60


class LimitReached(Exception):
    """Refused because the workspace's plan doesn't allow more. Shown to the user as is."""


@dataclass
class Usage:
    plan_name: str
    minutes_used: int
    minutes_limit: int | None
    agents: int
    agents_limit: int | None
    members: int
    members_limit: int | None

    @property
    def outbound_blocked(self) -> bool:
        return self.minutes_limit is not None and self.minutes_used >= self.minutes_limit


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def month_start(now: datetime | None = None) -> datetime:
    now = now or _now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def minutes_used(db: Session, tenant_id: str, now: datetime | None = None) -> int:
    """Call minutes this calendar month (UTC), inbound and outbound, rounded up."""
    seconds = db.query(func.coalesce(func.sum(CallLog.duration_seconds), 0)).filter(
        CallLog.tenant_id == tenant_id, CallLog.created_at >= month_start(now)).scalar()
    return math.ceil(int(seconds or 0) / 60)


def members_count(db: Session, tenant_id: str) -> int:
    """Active members plus pending invitations, so invitations can't get past the limit."""
    active = db.query(func.count(User.id)).filter(User.tenant_id == tenant_id, User.status == "active").scalar()
    pending = db.query(func.count(Invitation.id)).filter(
        Invitation.tenant_id == tenant_id, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None),
        Invitation.expires_at > _now()).scalar()
    return int(active or 0) + int(pending or 0)


def usage(db: Session, tenant: Tenant, now: datetime | None = None) -> Usage:
    plan = billing.plan_for_workspace(tenant)
    limits = plan.limits if plan else billing.Limits()
    return Usage(
        plan_name=tenant.plan or billing.FREE_PLAN,
        minutes_used=minutes_used(db, tenant.id, now),
        minutes_limit=limits.minutes_per_month,
        agents=int(db.query(func.count(Agent.id)).filter(Agent.tenant_id == tenant.id).scalar() or 0),
        agents_limit=limits.agents,
        members=members_count(db, tenant.id),
        members_limit=limits.members,
    )


def _tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise LimitReached("Workspace not found.")
    return tenant


def check_outbound(db: Session, tenant_id: str, calls: int = 1) -> None:
    u = usage(db, _tenant(db, tenant_id))
    if u.outbound_blocked:
        raise LimitReached(f"Your {u.plan_name} plan's {u.minutes_limit:,} call minutes for this month are used up, so "
                           "outbound calls are paused until next month. Inbound calls are still answered. "
                           "Upgrade on the Billing page to call now.")


def check_new_agent(db: Session, tenant_id: str) -> None:
    u = usage(db, _tenant(db, tenant_id))
    if u.agents_limit is not None and u.agents >= u.agents_limit:
        raise LimitReached(f"Your {u.plan_name} plan allows {u.agents_limit} AI agent{'s' if u.agents_limit != 1 else ''}. "
                           "Delete one or upgrade on the Billing page to add more.")


def check_new_member(db: Session, tenant_id: str) -> None:
    u = usage(db, _tenant(db, tenant_id))
    if u.members_limit is not None and u.members >= u.members_limit:
        raise LimitReached(f"Your {u.plan_name} plan allows {u.members_limit} team members, including pending "
                           "invitations. Remove someone or upgrade on the Billing page to invite more.")


# --- Heads-up at 80% and 100% of the monthly minutes ---------------------------------------------

def _alert_kind(level: str) -> str:
    return f"usage_{level}"


def check_alerts(now: datetime | None = None) -> int:
    """Notify and email Owners and Admins when a workspace passes 80% or 100% of its minutes. Returns alerts sent."""
    from app.services import notifications
    from app.services.mailer import deliver
    now = now or _now()
    sent = 0
    db = SessionLocal()
    plans = billing.load_plans()
    if not any(p.limits.minutes_per_month is not None for p in plans):
        return 0
    try:
        for tenant in db.query(Tenant).all():
            plan = billing.plan_for_workspace(tenant, plans)
            if plan is None or plan.limits.minutes_per_month is None:
                continue
            limit = plan.limits.minutes_per_month
            used = minutes_used(db, tenant.id, now)
            level = "limit" if used >= limit else "warning" if used >= math.ceil(limit * WARN_AT) else None
            if level is None:
                continue
            already = db.query(Notification.id).filter(
                Notification.tenant_id == tenant.id, Notification.kind == _alert_kind(level),
                Notification.created_at >= month_start(now)).first()
            if already:
                continue
            admins = db.query(User).filter(User.tenant_id == tenant.id, User.status == "active",
                                           User.role.in_(("Owner", "Admin"))).all()
            if level == "limit":
                title = f"All {limit:,} call minutes for this month are used"
                body = "Outbound calls and campaigns are paused until next month; inbound calls are still answered."
            else:
                title = f"{used:,} of {limit:,} call minutes used this month"
                body = "Outbound calls and campaigns pause when the limit is reached; inbound calls are still answered."
            notifications.notify(db, tenant.id, [u.id for u in admins], kind=_alert_kind(level), title=title,
                                 body=body, link="/billing")
            for admin in admins:
                deliver(admin.email, f"aVn: {title}", f"{title} on the {plan.name} plan.\n\n{body}\n\n"
                                                      f"Upgrade or check usage: {settings.frontend_base_url}/billing")
            sent += 1
        return sent
    finally:
        db.close()
