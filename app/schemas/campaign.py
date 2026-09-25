from app.schemas.common import UTCDateTime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CampaignLeadIn(BaseModel):
    phone: str
    name: str = ""
    email: Optional[str] = None
    custom_fields: Dict[str, Any] = {}


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    agent_id: Optional[str] = None
    concurrency_limit: int = Field(default=5, ge=1, le=50)
    retry_limit: int = Field(default=2, ge=0, le=10)
    leads: List[CampaignLeadIn] = []


class CampaignLeadOut(BaseModel):
    id: str
    name: str
    phone: str
    status: str
    outcome: Optional[str] = None
    attempts: int = 0
    custom_fields: Dict[str, Any] = {}


class CampaignOut(BaseModel):
    id: str
    name: str
    status: str
    agent_id: Optional[str] = None
    concurrency_limit: int
    retry_limit: int
    created_at: UTCDateTime
    total_leads: int = 0
    completed_leads: int = 0
    qualified_leads: int = 0
    scheduled_leads: int = 0
    failed_leads: int = 0


class CampaignDetailOut(CampaignOut):
    leads: List[CampaignLeadOut] = []
