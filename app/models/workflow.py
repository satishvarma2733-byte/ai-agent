import uuid
from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, Integer, UniqueConstraint
from app.core.database import Base
from app.models.base import TimestampMixin

class Workflow(Base, TimestampMixin):
    """Workflow represents automated action sequences triggered by CRM state transitions or time offsets."""
    __tablename__ = "workflows"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(150), nullable=False)
    trigger_event = Column(String(150), nullable=False)  # trigger events: lead_created | status_changed | call_completed
    actions_json = Column(Text, nullable=False)  # Encoded list of WorkflowActions
    is_active = Column(Boolean, default=True, nullable=False)
    # Trigger settings as JSON, e.g. {"minutes_before": 1440} for appointment reminders.
    trigger_config = Column(Text, nullable=True)

class WorkflowLog(Base):
    """WorkflowLog lists executions of automated sequences detailing outcomes or error states."""
    __tablename__ = "workflow_logs"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    workflow_id = Column(String(50), ForeignKey("workflows.id", ondelete="CASCADE"), index=True, nullable=False)
    triggered_at = Column(DateTime, nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # success | failed | pending
    message = Column(Text, nullable=True)

class WorkflowEvent(Base):
    """Durable queue of workflow triggers. Written by the API and the voice worker (separate process);
    the API's workflow engine claims and runs them. `ref` makes an event idempotent (e.g. one
    call_completed per call room)."""
    __tablename__ = "workflow_events"
    __table_args__ = (UniqueConstraint("tenant_id", "event_type", "ref"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type = Column(String(100), nullable=False)
    lead_id = Column(String(50), nullable=True)
    phone = Column(String(50), nullable=True)
    ref = Column(String(150), nullable=True)
    created_at = Column(DateTime, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)


class WebhookEndpoint(Base):
    """A workspace's secret inbound URL for creating leads (e.g. from website forms), plus the
    secret used to sign outbound webhook calls. Only the token's hash is stored."""
    __tablename__ = "webhook_endpoints"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    signing_secret = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
