from pydantic import BaseModel
from typing import Literal, Optional
from app.schemas.common import UTCDateTime

class AppointmentBase(BaseModel):
    title: str = "Appointment"
    contact_name: str
    contact_phone: str
    scheduled_start: str
    scheduled_end: str
    timezone: str = "Asia/Kolkata"
    status: str = "scheduled"
    notes: Optional[str] = None
    source: str = "voice_agent"

AppointmentStatus = Literal["scheduled", "completed", "cancelled"]

class AppointmentCreate(BaseModel):
    title: str = "Appointment"
    contact_name: str
    contact_phone: str
    scheduled_start: str
    scheduled_end: str
    timezone: Optional[str] = "Asia/Kolkata"
    status: Optional[AppointmentStatus] = "scheduled"
    notes: Optional[str] = None

class AppointmentUpdate(BaseModel):
    title: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    timezone: Optional[str] = None
    status: Optional[AppointmentStatus] = None
    notes: Optional[str] = None

class AppointmentOut(AppointmentBase):
    id: str
    created_at: UTCDateTime
    updated_at: UTCDateTime

    class Config:
        from_attributes = True
