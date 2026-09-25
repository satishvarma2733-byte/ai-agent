import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.core.database import Base


class Notification(Base):
    """Something a member should know about (a lead assigned to them, a missed call, a failed workflow)."""
    __tablename__ = "notifications"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(50), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind = Column(String(40), nullable=False)  # lead_assigned | call_missed | appointment_booked | workflow_failed
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String(300), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
