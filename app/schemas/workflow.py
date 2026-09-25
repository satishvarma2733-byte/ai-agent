from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.schemas.common import UTCDateTime

class WorkflowAction(BaseModel):
    type: str  # ai_call | whatsapp | reminder | crm_update
    config: Dict[str, Any]

class WorkflowBase(BaseModel):
    name: str
    trigger_event: str  # trigger events: lead_created | status_changed | call_completed
    is_active: bool = True
    # appointment_reminder: {"minutes_before": 15..10080}, default 1440 (a day)
    trigger_config: Optional[Dict[str, Any]] = None

class WorkflowCreate(WorkflowBase):
    actions: List[WorkflowAction]

class WorkflowOut(WorkflowBase):
    id: str
    actions: List[WorkflowAction]
    created_at: UTCDateTime

    class Config:
        from_attributes = True

class WorkflowLogOut(BaseModel):
    id: str
    workflow_id: str
    triggered_at: UTCDateTime
    status: str
    message: Optional[str] = None

    class Config:
        from_attributes = True
