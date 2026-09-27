"""Workspace memberships: who belongs to which workspace, with which role.

An authenticated request works in its session's workspace. `apply_workspace` puts that workspace and the
person's role there onto the request's User object as committed (not dirty) values, so existing code that reads
`current_user.tenant_id` / `current_user.role` sees the session's workspace, and nothing writes it back to the
users row. A listener re-applies them after the object is refreshed (e.g. expired by a commit).

Anything about *other* people in a workspace (member lists, managers to notify, assignees) must go through
memberships, never users.tenant_id / users.role.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import event
from sqlalchemy.orm import Query, Session
from sqlalchemy.orm.attributes import set_committed_value

from app.models.membership import Membership
from app.models.user import User

_WORKSPACE_ATTR = "_avn_workspace"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get(db: Session, user_id: str, tenant_id: str) -> Membership | None:
    return db.query(Membership).filter(Membership.user_id == user_id, Membership.tenant_id == tenant_id).first()


def active(db: Session, user_id: str, tenant_id: str) -> Membership | None:
    m = get(db, user_id, tenant_id)
    return m if m is not None and m.status == "active" else None


def add(db: Session, user: User, tenant_id: str, role: str) -> Membership:
    m = get(db, user.id, tenant_id)
    if m is None:
        m = Membership(user_id=user.id, tenant_id=tenant_id, role=role, status="active", created_at=_now())
        db.add(m)
    else:
        m.role, m.status = role, "active"
    return m


def ensure_home(db: Session, user: User) -> None:
    """Accounts from before memberships existed get one from users.tenant_id / users.role."""
    if db.query(Membership.id).filter(Membership.user_id == user.id).first() is None:
        # Deactivating a teammate used to set users.status; that now belongs to the membership.
        db.add(Membership(user_id=user.id, tenant_id=user.tenant_id, role=user.role or "Agent",
                          status="active" if user.status == "active" else "inactive", created_at=_now()))
        user.status = "active"
        db.flush()


def default_for(db: Session, user: User) -> Membership | None:
    """The workspace to sign in to: the last one used if still active there, else the oldest active one."""
    ensure_home(db, user)
    return active(db, user.id, user.tenant_id) or (
        db.query(Membership).filter(Membership.user_id == user.id, Membership.status == "active")
        .order_by(Membership.created_at).first())


def remember(db: Session, user: User, membership: Membership) -> None:
    """Make this the workspace the person's next sign-in starts in (and the request's workspace).
    A direct UPDATE, because the in-memory values may already equal the new ones and would not be flushed."""
    db.query(User).filter(User.id == user.id).update(
        {User.tenant_id: membership.tenant_id, User.role: membership.role}, synchronize_session=False)
    apply_workspace(user, membership)


def apply_workspace(user: User, membership: Membership) -> None:
    setattr(user, _WORKSPACE_ATTR, (membership.tenant_id, membership.role))
    _reapply(user)


def _reapply(user: User) -> None:
    ws = getattr(user, _WORKSPACE_ATTR, None)
    if ws:
        set_committed_value(user, "tenant_id", ws[0])
        set_committed_value(user, "role", ws[1])


@event.listens_for(User, "refresh")
def _after_refresh(target: User, context, attrs) -> None:
    _reapply(target)


# --- Other people in a workspace ---------------------------------------------------------------

def members(db: Session, tenant_id: str, *, active_only: bool = False, roles: tuple[str, ...] | None = None) -> Query:
    """(User, Membership) rows for a workspace. Active means active in the workspace and as an account."""
    q = db.query(User, Membership).join(Membership, Membership.user_id == User.id).filter(Membership.tenant_id == tenant_id)
    if active_only:
        q = q.filter(Membership.status == "active", User.status == "active")
    if roles:
        q = q.filter(Membership.role.in_(roles))
    return q


def member_users(db: Session, tenant_id: str, *, roles: tuple[str, ...] | None = None) -> list[User]:
    return [u for u, _ in members(db, tenant_id, active_only=True, roles=roles).all()]


def member_ids(db: Session, tenant_id: str, *, roles: tuple[str, ...] | None = None) -> list[str]:
    return [u.id for u in member_users(db, tenant_id, roles=roles)]


def is_active_member(db: Session, user_id: str, tenant_id: str) -> bool:
    return members(db, tenant_id, active_only=True).filter(User.id == user_id).first() is not None


def count_active(db: Session, tenant_id: str) -> int:
    return members(db, tenant_id, active_only=True).count()
