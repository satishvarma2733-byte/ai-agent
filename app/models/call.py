import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from app.core.database import Base
from app.models.base import TimestampMixin

class CallLog(Base, TimestampMixin):
    """Call log database schema mapping records of outbound and inbound call sessions."""
    __tablename__ = "call_logs"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    phone_number = Column(String(50), nullable=False)
    caller_name = Column(String(100), default="", nullable=False)
    duration_seconds = Column(Integer, default=0, nullable=False)
    summary = Column(Text, default="", nullable=False)
    transcript = Column(Text, nullable=True)
    recording_url = Column(String(500), nullable=True)
    sentiment = Column(String(50), default="unknown", nullable=False)
    was_booked = Column(Boolean, default=False, nullable=False)
    interrupt_count = Column(Integer, default=0, nullable=False)
    estimated_cost_usd = Column(Float, default=0.0, nullable=False)
    call_date = Column(String(50), nullable=True)
    call_hour = Column(Integer, nullable=True)
    call_day_of_week = Column(String(50), nullable=True)
    call_room_id = Column(String(100), index=True, nullable=True)
    direction = Column(String(50), default="outbound", nullable=False)  # inbound | outbound
    agent_id = Column(String(50), nullable=True)
    # The emailed call summary: when it was handled and how (sent | logged | failed | skipped).
    summary_sent_at = Column(DateTime, nullable=True)
    summary_email_status = Column(String(20), nullable=True)

class CallTurnMetric(Base, TimestampMixin):
    """Turn metrics tracking system latency indicators (STT, KB, LLM, TTS) for every call turn."""
    __tablename__ = "call_turn_metrics"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    call_room_id = Column(String(100), index=True, nullable=False)
    phone_number = Column(String(50), nullable=True)
    turn_index = Column(Integer, nullable=False)
    speaker = Column(String(50), default="assistant", nullable=False)  # assistant | user
    
    # Latency components (in milliseconds)
    stt_endpoint_ms = Column(Float, nullable=True)
    kb_ms = Column(Float, nullable=True)
    llm_first_token_ms = Column(Float, nullable=True)
    tts_first_audio_ms = Column(Float, nullable=True)
    tool_ms = Column(Float, nullable=True)
    total_turn_ms = Column(Float, nullable=True)

    kb_used = Column(Boolean, default=False, nullable=False)
    kb_skipped_reason = Column(String(250), nullable=True)
    metadata_json = Column(Text, nullable=True)
