"""Sessions (rotating refresh tokens) and single-use emailed tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    hash_token,
    new_opaque_token,
)
from app.models.auth import AuthSession, AuthToken
from app.models.user import User

VERIFY_EMAIL_TTL = timedelta(hours=48)
RESET_PASSWORD_TTL = timedelta(hours=1)
INVITATION_TTL = timedelta(days=7)
# A just-rotated refresh token presented again within this window is a concurrent refresh, not a replay.
REFRESH_REUSE_GRACE = timedelta(seconds=30)


def utcnow() -> datetime:
    # Naive UTC, matching the DateTime columns.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SessionError(Exception):
    pass


def issue_access_token(user: User, session: AuthSession) -> str:
    return create_access_token(
        {"sub": user.email, "sid": session.id, "tid": user.tenant_id, "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_session(db: Session, user: User, *, user_agent: str | None, ip: str | None) -> tuple[str, str]:
    """Start a session. Returns (access_token, refresh_token)."""
    refresh = new_opaque_token()
    now = utcnow()
    session = AuthSession(
        tenant_id=user.tenant_id,
        user_id=user.id,
        refresh_token_hash=hash_token(refresh),
        user_agent=(user_agent or "")[:300] or None,
        ip=ip,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    user.last_seen = now.isoformat()
    db.commit()
    db.refresh(session)
    return issue_access_token(user, session), refresh


def rotate_session(db: Session, refresh_token: str) -> tuple[User, str, str]:
    """Exchange a refresh token for a new pair. Replaying an already-rotated token revokes
    every session of that user (the token was copied)."""
    token_hash = hash_token(refresh_token)
    now = utcnow()
    session = db.query(AuthSession).filter(AuthSession.refresh_token_hash == token_hash).first()
    if session is None:
        replayed = db.query(AuthSession).filter(AuthSession.previous_token_hash == token_hash).first()
        if replayed is None:
            raise SessionError("Invalid refresh token")
        if replayed.revoked_at is None and now - replayed.last_used_at <= REFRESH_REUSE_GRACE:
            # Two tabs (or a reload racing a refresh) sent the same cookie at once: not theft.
            # Rotate again; the browser keeps whichever cookie arrives last, and both are valid for it.
            session = replayed
        else:
            revoke_all_sessions(db, replayed.user_id)
            raise SessionError("Invalid refresh token")
    if session.revoked_at is not None or session.expires_at <= now:
        raise SessionError("Session expired")
    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or user.status != "active":
        raise SessionError("User not found or inactive")

    new_refresh = new_opaque_token()
    session.previous_token_hash = token_hash
    session.refresh_token_hash = hash_token(new_refresh)
    session.last_used_at = now
    user.last_seen = now.isoformat()
    db.commit()
    return user, issue_access_token(user, session), new_refresh


def session_is_active(db: Session, session_id: str) -> bool:
    session = db.query(AuthSession).filter(AuthSession.id == session_id).first()
    return session is not None and session.revoked_at is None and session.expires_at > utcnow()


def revoke_session(db: Session, session_id: str) -> None:
    db.query(AuthSession).filter(AuthSession.id == session_id, AuthSession.revoked_at.is_(None)).update(
        {AuthSession.revoked_at: utcnow()}, synchronize_session=False
    )
    db.commit()


def revoke_all_sessions(db: Session, user_id: str) -> None:
    db.query(AuthSession).filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).update(
        {AuthSession.revoked_at: utcnow()}, synchronize_session=False
    )
    db.commit()


def issue_user_token(db: Session, user: User, purpose: str) -> str:
    """Create a single-use token (verify_email / reset_password); earlier unused ones are invalidated."""
    ttl = VERIFY_EMAIL_TTL if purpose == "verify_email" else RESET_PASSWORD_TTL
    now = utcnow()
    db.query(AuthToken).filter(
        AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None)
    ).update({AuthToken.used_at: now}, synchronize_session=False)
    token = new_opaque_token()
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=hash_token(token), created_at=now, expires_at=now + ttl))
    db.commit()
    return token


def consume_user_token(db: Session, token: str, purpose: str) -> User | None:
    now = utcnow()
    row = db.query(AuthToken).filter(AuthToken.token_hash == hash_token(token), AuthToken.purpose == purpose).first()
    if row is None or row.used_at is not None or row.expires_at <= now:
        return None
    row.used_at = now
    user = db.query(User).filter(User.id == row.user_id).first()
    db.commit()
    return user
