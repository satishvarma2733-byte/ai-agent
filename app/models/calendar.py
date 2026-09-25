import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.core.database import Base


class CalendarConnection(Base):
    """A workspace's link to an external calendar (one per provider). Tokens are encrypted at rest."""
    __tablename__ = "calendar_connections"
    __table_args__ = (UniqueConstraint("tenant_id", "provider"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    provider = Column(String(20), nullable=False)  # google | zoho
    account_email = Column(String(200), nullable=True)
    calendar_id = Column(String(200), nullable=False)
    # Zoho serves each data centre from its own domains (accounts.zoho.in, calendar.zoho.in, ...).
    accounts_url = Column(String(200), nullable=True)
    refresh_token = Column(Text, nullable=False)
    access_token = Column(Text, nullable=True)
    access_expires_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="active", nullable=False)  # active | error
    last_error = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    connected_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)


class AppointmentCalendarEvent(Base):
    """The external event mirroring one appointment in one connected calendar, and whether it is up to date."""
    __tablename__ = "appointment_calendar_events"
    __table_args__ = (UniqueConstraint("appointment_id", "connection_id"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    appointment_id = Column(String(50), ForeignKey("appointments.id", ondelete="CASCADE"), index=True, nullable=False)
    connection_id = Column(String(50), ForeignKey("calendar_connections.id", ondelete="CASCADE"), index=True, nullable=False)
    external_id = Column(String(300), nullable=True)
    etag = Column(String(300), nullable=True)
    # Start/end last written to or read from the calendar, to tell our changes from the owner's.
    synced_start = Column(String(100), nullable=True)
    synced_end = Column(String(100), nullable=True)
    state = Column(String(20), default="pending", nullable=False, index=True)  # pending | synced | error
    attempts = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False)
