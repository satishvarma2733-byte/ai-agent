import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from app.core.database import Base

class AuditLog(Base):
    """AuditLog represents administrative logging entries detailing user actions and modifications."""
    __tablename__ = "audit_logs"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="SET NULL"), index=True, nullable=True)
    user_id = Column(String(50), index=True, nullable=True)  # Associated user performing the change
    action = Column(String(100), nullable=False)              # e.g. login | create_lead | delete_faq
    entity = Column(String(100), nullable=False)              # e.g. Lead | User | FAQ
    entity_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
