import uuid
from sqlalchemy import Column, String, Text
from app.core.database import Base
from app.models.base import TimestampMixin

class Tenant(Base, TimestampMixin):
    """SaaS Tenant corporate profile containing subscription configuration."""
    __tablename__ = "tenants"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(150), nullable=False)
    subdomain = Column(String(100), unique=True, index=True, nullable=True)
    plan = Column(String(50), default="Free", nullable=False)  # Free | Growth | Enterprise
    status = Column(String(50), default="active", nullable=False)  # active | suspended
    # Who gets an email after each call, as JSON (see app/services/call_summaries.py). Empty = off.
    call_summaries = Column(Text, nullable=True)
