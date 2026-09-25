import uuid
from sqlalchemy import Column, String, Text, ForeignKey
from app.core.database import Base
from app.models.base import TimestampMixin

class Appointment(Base, TimestampMixin):
    """Appointment scheduling model representing customer bookings and schedules."""
    __tablename__ = "appointments"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(150), default="Appointment", nullable=False)
    contact_name = Column(String(100), nullable=False)
    contact_phone = Column(String(50), nullable=False)
    scheduled_start = Column(String(100), nullable=False)  # ISO Datetime format
    scheduled_end = Column(String(100), nullable=False)    # ISO Datetime format
    timezone = Column(String(100), default="Asia/Kolkata", nullable=False)
    status = Column(String(50), default="scheduled", nullable=False)  # scheduled | cancelled | completed
    notes = Column(Text, nullable=True)
    source = Column(String(100), default="voice_agent", nullable=False)  # voice_agent | manual_ui
