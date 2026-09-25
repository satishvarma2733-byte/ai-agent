import re
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator
from app.schemas.common import UTCDateTime

LeadStatus = Literal["New", "Contacted", "Follow-up", "Interested", "Converted", "Lost"]
LeadScore = Literal["Hot", "Warm", "Cold"]
_PHONE_SEPARATORS = re.compile(r"[\s().-]")
_E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")


def _blank_to_none(value):
    # Forms send "" for untouched optional fields; an empty email is "no email", not an invalid one.
    return None if isinstance(value, str) and not value.strip() else value


def _follow_up(value):
    """Follow-up dates are calendar days (YYYY-MM-DD); a full ISO time keeps just its date."""
    value = _blank_to_none(value)
    if value is None:
        return None
    from datetime import date, datetime
    text = str(value).strip()
    try:
        return (date.fromisoformat(text) if len(text) == 10 else datetime.fromisoformat(text.replace("Z", "+00:00")).date()).isoformat()
    except ValueError:
        raise ValueError("Follow-up date must be a date like 2026-10-01")


def normalize_phone(value: str) -> str:
    """Strip separators and require international (E.164) form, e.g. +919876543210."""
    phone = _PHONE_SEPARATORS.sub("", value or "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not _E164.match(phone):
        raise ValueError("Enter the phone number with its country code, e.g. +919876543210")
    return phone


class LeadBase(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    company: Optional[str] = None
    status: LeadStatus = "New"
    score: LeadScore = "Cold"
    score_explanation: Optional[str] = None
    assigned_agent: Optional[str] = None
    assigned_user_id: Optional[str] = None
    budget: Optional[str] = None
    state: Optional[str] = None
    neet_score: Optional[int] = None
    rank: Optional[int] = None
    parent_involved: bool = False
    country_preference: Optional[str] = None
    follow_up_date: Optional[str] = None
    objection: Optional[str] = None
    session_booked: bool = False
    notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None

class LeadCreate(LeadBase):
    _blank_email = field_validator("email", "assigned_user_id", mode="before")(_blank_to_none)
    _follow_up_date = field_validator("follow_up_date", mode="before")(_follow_up)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    company: Optional[str] = None
    status: Optional[LeadStatus] = None
    score: Optional[LeadScore] = None
    score_explanation: Optional[str] = None
    assigned_agent: Optional[str] = None
    assigned_user_id: Optional[str] = None
    budget: Optional[str] = None
    state: Optional[str] = None
    neet_score: Optional[int] = None
    rank: Optional[int] = None
    parent_involved: Optional[bool] = None
    country_preference: Optional[str] = None
    follow_up_date: Optional[str] = None
    objection: Optional[str] = None
    session_booked: Optional[bool] = None
    notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None

    _blank_email = field_validator("email", "assigned_user_id", mode="before")(_blank_to_none)
    _follow_up_date = field_validator("follow_up_date", mode="before")(_follow_up)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_phone(value)

class LeadOut(LeadBase):
    # Rows saved before validation may hold any text.
    status: str
    score: str

    id: str
    created_at: UTCDateTime
    updated_at: UTCDateTime

    class Config:
        from_attributes = True

class LeadActivityBase(BaseModel):
    activity_type: str  # call | note | whatsapp | crm_update | pipeline_change
    title: str
    description: str
    metadata_json: Optional[str] = None

class LeadActivityCreate(LeadActivityBase):
    pass

class LeadActivityOut(LeadActivityBase):
    id: str
    lead_id: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True
