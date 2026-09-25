"""In-app notifications for workspace members. Safe to call from the API or the voice worker."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger("notifications")

MANAGERS = ("Owner", "Admin", "Manager")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def managers(db: Session, tenant_id: str) -> list[str]:
    return [u.id for u in db.query(User.id).filter(User.tenant_id == tenant_id, User.status == "active",
                                                   User.role.in_(MANAGERS))]


def notify(db: Session, tenant_id: str, user_ids: Iterable[str | None], *, kind: str, title: str,
           body: str | None = None, link: str | None = None) -> int:
    """One notification per (distinct, active, same-workspace) recipient. Never raises."""
    try:
        wanted = {u for u in user_ids if u}
        if not wanted:
            return 0
        members = {u.id for u in db.query(User.id).filter(User.tenant_id == tenant_id, User.status == "active", User.id.in_(wanted))}
        now = _now()
        for user_id in members:
            db.add(Notification(tenant_id=tenant_id, user_id=user_id, kind=kind, title=title[:200], body=body, link=link, created_at=now))
        db.commit()
        return len(members)
    except Exception as exc:
        db.rollback()
        logger.error("Could not create %s notifications: %s", kind, exc)
        return 0


def notify_new_session(tenant_id: str, user_ids: Iterable[str | None], **kwargs) -> int:
    """For code without a request-scoped session (voice worker, background tasks)."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        return notify(db, tenant_id, user_ids, **kwargs)
    finally:
        db.close()
