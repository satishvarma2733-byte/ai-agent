from pydantic import BaseModel, EmailStr, Field
from app.schemas.common import UTCDateTime
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: str = "Agent"
    status: str = "active"
    phone: Optional[str] = None
    calls: int = 0
    success: float = 0.0
    joined: Optional[str] = None
    last_seen: Optional[str] = None

class UserCreate(BaseModel):
    """Public signup payload. Always creates a new tenant owned by this user;
    tenant and role are never taken from the client."""
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    company_name: Optional[str] = Field(default=None, max_length=150)

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    phone: Optional[str] = None

class UserOut(UserBase):
    id: str
    tenant_id: Optional[str] = None
    email_verified_at: Optional[UTCDateTime] = None

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None
