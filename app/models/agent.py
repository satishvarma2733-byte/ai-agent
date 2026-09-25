import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.models.base import TimestampMixin


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Agent(Base, TimestampMixin):
    """Agent identity. Its behaviour lives in immutable AgentVersion snapshots."""
    __tablename__ = "agents"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    tags_csv = Column(String(250), nullable=True)
    # Runtime presence reported by the voice worker: active | idle | offline | processing
    status = Column(String(50), default="idle", nullable=False)
    production_version_id = Column(String(50), ForeignKey("agent_versions.id", ondelete="SET NULL", use_alter=True), nullable=True)
    draft_version_id = Column(String(50), ForeignKey("agent_versions.id", ondelete="SET NULL", use_alter=True), nullable=True)
    disabled_at = Column(DateTime, nullable=True)
    created_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Call statistics (to be derived from analytics events in Milestone 4)
    calls_today = Column(Integer, default=0, nullable=False)
    calls_total = Column(Integer, default=0, nullable=False)
    avg_duration = Column(Integer, default=0, nullable=False)
    success_rate = Column(Float, default=0.0, nullable=False)
    last_active = Column(String(100), nullable=True)


class AgentVersion(Base):
    """Immutable (once out of draft) snapshot of an agent's configuration."""
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "number"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id = Column(String(50), ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    number = Column(Integer, nullable=False)
    # draft | testing | evaluation | approved | production | superseded | rejected
    status = Column(String(30), default="draft", nullable=False)
    config = Column(JSON, nullable=False)
    based_on_version_id = Column(String(50), nullable=True)
    created_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)
    approved_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)


class AgentChange(Base):
    """One recorded edit to a draft: who, when, why, and which fields changed."""
    __tablename__ = "agent_changes"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id = Column(String(50), ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    version_id = Column(String(50), ForeignKey("agent_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(30), default="ui", nullable=False)  # ui | copilot | testing_agent | api | import
    reason = Column(Text, nullable=False)
    changes = Column(JSON, nullable=False)  # [{"path": "voice.voice", "before": ..., "after": ...}]
    created_at = Column(DateTime, default=_now, nullable=False)


class AgentLifecycleEvent(Base):
    __tablename__ = "agent_lifecycle_events"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id = Column(String(50), ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    version_id = Column(String(50), ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=True)
    action = Column(String(30), nullable=False)
    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=True)
    user_id = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)


class AgentPhoneNumber(Base):
    """A business phone number answered by one agent. Numbers are unique across all workspaces
    because an incoming call to a number must route to exactly one agent."""
    __tablename__ = "agent_phone_numbers"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id = Column(String(50), ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
