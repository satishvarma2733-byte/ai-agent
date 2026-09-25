from app.schemas.common import UTCDateTime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

Lifecycle = Literal["draft", "testing", "evaluation", "approved", "production", "rejected", "disabled"]
VersionStatus = Literal["draft", "testing", "evaluation", "approved", "production", "superseded", "rejected"]


class AgentCompatFields(BaseModel):
    """Flat fields used by the Agents page; stored inside the draft version's config."""
    voice: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    instructions: Optional[str] = None
    language: Optional[str] = None
    greeting: Optional[str] = None
    max_call_duration: Optional[int] = None
    fallback_phone: Optional[str] = None
    working_hours_start: Optional[str] = None
    working_hours_end: Optional[str] = None
    working_days: Optional[List[str]] = None


class AgentCreate(AgentCompatFields):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    tags: List[str] = []


class AgentUpdate(AgentCompatFields):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class AgentOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = []
    status: str  # runtime presence reported by the voice worker
    lifecycle: Lifecycle
    production_version: Optional[int] = None
    draft_version: Optional[int] = None
    calls_today: int = 0
    calls_total: int = 0
    avg_duration: int = 0
    success_rate: float = 0.0
    last_active: Optional[str] = None
    # Current editable configuration (draft if present, else production), flattened.
    voice: str
    model: str
    temperature: float
    instructions: str
    language: str
    greeting: str
    max_call_duration: int
    fallback_phone: str
    working_hours_start: str
    working_hours_end: str
    working_days: List[str]


class VersionOut(BaseModel):
    id: str
    number: int
    status: VersionStatus
    config: dict[str, Any]
    based_on_version_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    approved_at: Optional[UTCDateTime] = None
    activated_at: Optional[UTCDateTime] = None


class ConfigChange(BaseModel):
    path: str
    before: Any = None
    after: Any = None


class DraftPatchIn(BaseModel):
    patch: dict[str, Any]
    reason: str = Field(min_length=3, max_length=500)


class DraftPatchOut(BaseModel):
    version: VersionOut
    changes: List[ConfigChange]


class TransitionIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class ChangeOut(BaseModel):
    id: str
    version_number: int
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    source: str
    reason: str
    changes: List[ConfigChange]
    created_at: UTCDateTime


class LifecycleEventOut(BaseModel):
    id: str
    version_number: Optional[int] = None
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    user_name: Optional[str] = None
    note: Optional[str] = None
    created_at: UTCDateTime


class VersionDiffOut(BaseModel):
    from_version: int
    to_version: int
    changes: List[ConfigChange]
