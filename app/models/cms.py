import uuid
from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey, UniqueConstraint
from app.core.database import Base
from app.models.base import TimestampMixin

class CMSPage(Base, TimestampMixin):
    """CMSPage represents customizable site pages and content chunks managed via the dashboard."""
    __tablename__ = "cms_pages"
    __table_args__ = (UniqueConstraint("tenant_id", "slug"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    # Unique within a tenant (see __table_args__), not across tenants.
    slug = Column(String(200), index=True, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(50), default="published", nullable=False)  # published | draft | archived
    category = Column(String(100), nullable=True)
    seo_title = Column(String(200), nullable=True)
    seo_description = Column(Text, nullable=True)

class CMSPrompt(Base, TimestampMixin):
    """CMSPrompt stores active system instructions utilized by the Voice Agent LLM configurations."""
    __tablename__ = "cms_prompts"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(150), nullable=False)
    content = Column(Text, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    tags_csv = Column(String(250), nullable=True)  # Comma-separated tags

class CMSFaq(Base):
    """CMSFaq represents question and answer sheets queried by customers or agents during groundings."""
    __tablename__ = "cms_faqs"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    question = Column(String(300), nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String(100), nullable=True)
    order = Column(Integer, default=0, nullable=False)

class CMSMedia(Base, TimestampMixin):
    """CMSMedia indexes static assets and PDF manuals uploaded to S3 storage bucket setups."""
    __tablename__ = "cms_media"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    filename = Column(String(250), nullable=False)
    url = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, default=0, nullable=False)
