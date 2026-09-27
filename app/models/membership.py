import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint

from app.core.database import Base


class Membership(Base):
    """A person's place in one workspace: their role and whether they're active there.

    One account (users row, one email and password) can belong to several workspaces. Each signed-in device
    works in one of them at a time (auth_sessions.tenant_id); users.tenant_id and users.role only remember the
    workspace the person used last, for their next sign-in."""
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_workspace_memberships_user_tenant"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="active")  # active | inactive
    created_at = Column(DateTime, nullable=False)
