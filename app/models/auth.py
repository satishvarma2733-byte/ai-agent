import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuthSession(Base):
    """A signed-in device. Holds the hash of its current (rotating) refresh token."""
    __tablename__ = "auth_sessions"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(50), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    refresh_token_hash = Column(String(64), unique=True, nullable=False)
    # Hash of the previous refresh token; presenting it again means the token was stolen and replayed.
    previous_token_hash = Column(String(64), index=True, nullable=True)
    user_agent = Column(String(300), nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    last_used_at = Column(DateTime, default=_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class AuthToken(Base):
    """Single-use emailed token: email verification or password reset."""
    __tablename__ = "auth_tokens"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    purpose = Column(String(30), nullable=False)  # verify_email | reset_password
    token_hash = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class Invitation(Base):
    """Invitation for someone to join a tenant with a given role."""
    __tablename__ = "invitations"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    email = Column(String(100), index=True, nullable=False)
    role = Column(String(50), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    invited_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
