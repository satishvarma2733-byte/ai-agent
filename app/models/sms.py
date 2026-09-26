import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.core.database import Base


class SmsAccount(Base):
    """A workspace's SMS sender (Twilio). Credentials are encrypted at rest."""
    __tablename__ = "sms_accounts"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    provider = Column(String(20), nullable=False)  # twilio
    sender = Column(String(20), nullable=False)
    credentials = Column(Text, nullable=False)  # sealed JSON
    connected_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class CalendarFeed(Base):
    """A workspace's secret iCalendar feed URL. Only the token's hash finds the workspace; the sealed copy
    lets admins see the URL again."""
    __tablename__ = "calendar_feeds"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    token = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    last_fetched_at = Column(DateTime, nullable=True)
