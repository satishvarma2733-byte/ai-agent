from app.schemas.common import UTCDateTime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field

Role = Literal["Owner", "Admin", "Manager", "Agent", "Viewer"]
AssignableRole = Literal["Admin", "Manager", "Agent", "Viewer"]
MemberStatus = Literal["active", "inactive"]


class SignupAcceptedOut(BaseModel):
    """Identical for new and already-registered emails, so signup can't be used to discover accounts."""
    status: str = "accepted"
    message: str = "If this email can be used, your workspace is ready. Sign in, or check your inbox."


class AccessTokenOut(BaseModel):
    """The refresh token is set as an httpOnly cookie, never returned in the body."""
    access_token: str
    token_type: str = "bearer"


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetPasswordIn(TokenIn):
    password: str = Field(min_length=10, max_length=128)


class AcceptInvitationIn(TokenIn):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=128)


class InvitationPreviewOut(BaseModel):
    email: str
    role: Role
    tenant_name: str
    expires_at: UTCDateTime


class InvitationCreate(BaseModel):
    email: EmailStr
    role: AssignableRole = "Agent"


class InvitationOut(BaseModel):
    id: str
    email: str
    role: Role
    created_at: UTCDateTime
    expires_at: UTCDateTime


class InvitationCreatedOut(BaseModel):
    invitation: InvitationOut
    # Always returned so an admin can share the link even when email isn't configured.
    accept_url: str
    email_status: Literal["sent", "logged", "not_configured", "failed"]


class MemberOut(BaseModel):
    id: str
    name: str
    email: str
    role: Role
    status: MemberStatus
    phone: Optional[str] = None
    joined: Optional[str] = None
    last_seen: Optional[str] = None
    email_verified: bool = False


class MemberUpdate(BaseModel):
    role: Optional[AssignableRole] = None
    status: Optional[MemberStatus] = None


class OwnershipTransferIn(BaseModel):
    user_id: str


class SessionOut(BaseModel):
    id: str
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    created_at: UTCDateTime
    last_used_at: UTCDateTime
    current: bool
