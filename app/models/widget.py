import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Text

from app.core.database import Base


class ChatWidget(Base):
    """A chat (and optional voice) bubble for the workspace's website. The public key sits in the site's HTML,
    so it isn't a secret: requests are accepted only from the listed origins."""
    __tablename__ = "chat_widgets"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id = Column(String(50), ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    public_key = Column(String(64), unique=True, nullable=False)
    allowed_origins = Column(JSON, nullable=False)
    greeting = Column(Text, nullable=True)
    color = Column(String(7), nullable=False, default="#7B61FF")
    voice_enabled = Column(Boolean, nullable=False, default=False)
    lead_capture = Column(Boolean, nullable=False, default=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class ApiKey(Base):
    """A secret key for the public chat API, for calling it from a server. Only the hash is stored."""
    __tablename__ = "api_keys"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    prefix = Column(String(16), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False)
    created_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class ChatSession(Base):
    """One website or API conversation. The visitor holds a session token; only its hash is stored."""
    __tablename__ = "chat_sessions"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id = Column(String(50), ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    widget_id = Column(String(50), ForeignKey("chat_widgets.id", ondelete="SET NULL"), index=True, nullable=True)
    api_key_id = Column(String(50), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    token_hash = Column(String(64), unique=True, nullable=False)
    turns = Column(JSON, nullable=False)
    origin = Column(String(200), nullable=True)
    lead_id = Column(String(50), ForeignKey("leads.id", ondelete="SET NULL"), index=True, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
