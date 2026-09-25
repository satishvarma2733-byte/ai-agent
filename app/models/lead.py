import uuid
from sqlalchemy import JSON, Column, String, Integer, Boolean, Text, ForeignKey, DateTime, UniqueConstraint
from app.core.database import Base
from app.models.base import TimestampMixin, SoftDeleteMixin

class Lead(Base, TimestampMixin, SoftDeleteMixin):
    """Lead model storing CRM contact profile details, workflow status, and agent assignments."""
    __tablename__ = "leads"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(50), nullable=False)
    email = Column(String(100), nullable=True)
    company = Column(String(100), nullable=True)
    status = Column(String(50), default="New", nullable=False)  # New | Contacted | Follow-up | Interested | Converted | Lost
    score = Column(String(50), default="Cold", nullable=False)  # Hot | Warm | Cold
    score_explanation = Column(Text, nullable=True)
    assigned_agent = Column(String(100), nullable=True)  # display name of the assignee
    assigned_user_id = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    
    # Custom qualifiers
    budget = Column(String(50), nullable=True)
    state = Column(String(100), nullable=True)
    neet_score = Column(Integer, nullable=True)
    rank = Column(Integer, nullable=True)
    parent_involved = Column(Boolean, default=False, nullable=False)
    country_preference = Column(String(150), nullable=True)
    follow_up_date = Column(String(50), nullable=True)
    objection = Column(Text, nullable=True)
    session_booked = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    # Values for the workspace's own fields (LeadField), keyed by field key.
    custom_fields = Column(JSON, nullable=True)

class LeadActivity(Base, TimestampMixin):
    """Activity tracking model detailing actions (calls, notes, messages) associated with a CRM Lead."""
    __tablename__ = "lead_activities"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    lead_id = Column(String(50), ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False)
    activity_type = Column(String(50), nullable=False)  # call | note | whatsapp | crm_update | pipeline_change
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)  # Encoded JSON metadata


class LeadField(Base, TimestampMixin):
    """A lead field a workspace defines for its own business (e.g. "Budget", "Course", "Property type")."""
    __tablename__ = "lead_fields"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    key = Column(String(60), nullable=False)  # stable slug used in custom_fields, imports and workflows
    label = Column(String(100), nullable=False)
    field_type = Column(String(20), nullable=False)  # text | number | date | select | boolean
    options = Column(JSON, nullable=True)  # choices for select
    position = Column(Integer, default=0, nullable=False)
