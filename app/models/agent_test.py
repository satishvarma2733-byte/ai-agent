import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class AgentTestCase(Base):
    """A scripted conversation an agent version must handle: what the caller says, and what the replies
    must and must not contain."""
    __tablename__ = "agent_test_cases"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id = Column(String(50), ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(150), nullable=False)
    caller_turns = Column(JSON, nullable=False)  # ["Hi, what are your timings?", "And on Sunday?"]
    must_include = Column(JSON, nullable=False, default=list)  # every phrase appears in some reply
    must_not_include = Column(JSON, nullable=False, default=list)  # no reply contains any of these
    expected_language = Column(String(10), nullable=True)  # replies must be in this language's script
    created_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False)


class AgentTestRun(Base):
    """One run of an agent's test cases against one version, with each case's transcript and verdict."""
    __tablename__ = "agent_test_runs"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id = Column(String(50), ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    version_id = Column(String(50), ForeignKey("agent_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    passed = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    results = Column(JSON, nullable=False)
    created_by = Column(String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, index=True, nullable=False)
