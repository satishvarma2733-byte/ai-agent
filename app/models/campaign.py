import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from app.core.database import Base
from app.models.base import TimestampMixin


class Campaign(Base, TimestampMixin):
    """Bulk outbound calling campaign dialled by the campaign worker."""
    __tablename__ = "campaigns"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(150), nullable=False)
    agent_id = Column(String(50), nullable=True)
    status = Column(String(50), default="queued", nullable=False)  # queued | running | paused | completed | failed
    concurrency_limit = Column(Integer, default=5, nullable=False)
    retry_limit = Column(Integer, default=2, nullable=False)


class CampaignLead(Base, TimestampMixin):
    """One number to dial within a campaign, linked to the CRM lead it came from."""
    __tablename__ = "campaign_leads"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    campaign_id = Column(String(50), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False)
    lead_id = Column(String(50), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), default="", nullable=False)
    phone = Column(String(50), nullable=False)
    status = Column(String(50), default="pending", index=True, nullable=False)  # pending | calling | completed | failed
    outcome = Column(String(50), nullable=True)  # booked | completed | short_call | no_answer | failed
    attempts = Column(Integer, default=0, nullable=False)
    call_room_id = Column(String(100), nullable=True)
    custom_fields_json = Column(Text, nullable=True)
    last_dispatched_at = Column(DateTime, nullable=True)
