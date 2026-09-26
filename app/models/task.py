import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.core.database import Base


class Task(Base):
    """A to-do for a teammate, optionally about a lead, with a due date."""
    __tablename__ = "tasks"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    lead_id = Column(String(50), ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=True)
    title = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)
    due_date = Column(String(10), nullable=True)  # YYYY-MM-DD, like lead follow-up dates
    assigned_user_id = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    status = Column(String(10), default="open", nullable=False)  # open | done
    created_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
