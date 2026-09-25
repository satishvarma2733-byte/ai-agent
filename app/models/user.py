import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from app.core.database import Base
from app.models.base import TimestampMixin

class User(Base, TimestampMixin):
    """System User/Team Member model representing Admins, Managers, and Agents."""
    __tablename__ = "users"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(50), default="Agent", nullable=False)  # Admin | Manager | Agent
    status = Column(String(50), default="active", nullable=False)  # active | inactive
    phone = Column(String(50), nullable=True)

    # Core performance metrics utilized in CRM / Leaderboards
    calls = Column(Integer, default=0, nullable=False)
    success = Column(Float, default=0.0, nullable=False)  # Success rate in %
    joined = Column(String(50), nullable=True)
    last_seen = Column(String(100), nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
