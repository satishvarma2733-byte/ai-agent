import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.core.database import Base


class WhatsAppAccount(Base):
    """A workspace's WhatsApp sender (Meta Cloud API or Twilio). Credentials are encrypted at rest."""
    __tablename__ = "whatsapp_accounts"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    provider = Column(String(20), nullable=False)  # meta | twilio
    sender = Column(String(50), nullable=True)  # the business number, for display
    credentials = Column(Text, nullable=False)  # sealed JSON
    # Secret part of this workspace's webhook URLs; the hash finds the workspace, the sealed copy shows the URL again.
    webhook_token_hash = Column(String(64), unique=True, nullable=False)
    webhook_token = Column(Text, nullable=False)
    status = Column(String(20), default="active", nullable=False)  # active | error
    last_error = Column(Text, nullable=True)
    connected_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class WhatsAppMessage(Base):
    """One WhatsApp message sent or received, with the delivery status the provider reports."""
    __tablename__ = "whatsapp_messages"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    lead_id = Column(String(50), ForeignKey("leads.id", ondelete="SET NULL"), index=True, nullable=True)
    phone = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)  # out | in
    body = Column(Text, nullable=True)
    template = Column(String(200), nullable=True)
    provider = Column(String(20), nullable=False)
    provider_message_id = Column(String(200), index=True, nullable=True)
    status = Column(String(20), nullable=False)  # sent | delivered | read | failed | received
    error = Column(Text, nullable=True)
    source = Column(String(20), nullable=False)  # manual | workflow | test | inbound
    created_at = Column(DateTime, index=True, nullable=False)
    updated_at = Column(DateTime, nullable=False)
