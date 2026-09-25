from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
from app.schemas.common import UTCDateTime
from app.services.signed_urls import sign_local_recording

class CallLogBase(BaseModel):
    phone_number: str
    caller_name: str = ""
    duration_seconds: int = 0
    summary: str = ""
    transcript: Optional[str] = None
    recording_url: Optional[str] = None
    sentiment: str = "unknown"
    was_booked: bool = False
    interrupt_count: int = 0
    estimated_cost_usd: float = 0.0
    call_date: Optional[str] = None
    call_hour: Optional[int] = None
    call_day_of_week: Optional[str] = None
    call_room_id: Optional[str] = None
    direction: str = "outbound"
    agent_id: Optional[str] = None

class CallLogCreate(CallLogBase):
    pass

class CallLogOut(CallLogBase):
    id: str
    created_at: UTCDateTime
    # Read from the row only to sign the recording link; never sent.
    tenant_id: Optional[str] = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _sign_recording(self):
        self.recording_url = sign_local_recording(self.tenant_id, self.recording_url)
        return self

    class Config:
        from_attributes = True

class CallTurnMetricBase(BaseModel):
    call_room_id: str
    phone_number: Optional[str] = None
    turn_index: int
    speaker: str = "assistant"
    stt_endpoint_ms: Optional[float] = None
    kb_ms: Optional[float] = None
    llm_first_token_ms: Optional[float] = None
    tts_first_audio_ms: Optional[float] = None
    tool_ms: Optional[float] = None
    total_turn_ms: Optional[float] = None
    kb_used: bool = False
    kb_skipped_reason: Optional[str] = None
    metadata_json: Optional[str] = None

class CallTurnMetricCreate(CallTurnMetricBase):
    pass

class CallTurnMetricOut(CallTurnMetricBase):
    id: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True


class LiveCallOut(BaseModel):
    id: str
    room: str
    phone_number: str
    caller_name: str = ""
    direction: str
    agent_id: Optional[str] = None
    participants: int
    started_at: UTCDateTime


class LiveCallsOut(BaseModel):
    configured: bool
    calls: List[LiveCallOut]
