import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.core.security import REFRESH_TOKEN_EXPIRE_DAYS, decode_token, get_password_hash, hash_token, verify_password
from app.core.settings import settings
from app.models.auth import AuthSession, Invitation
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    AcceptInvitationIn,
    AccessTokenOut,
    EmailIn,
    InvitationPreviewOut,
    SignupAcceptedOut,
    ResetPasswordIn,
    SessionOut,
    TokenIn,
)
from app.schemas.user import LoginRequest, UserCreate, UserOut
from app.services import audit
from app.services.auth_service import (
    SessionError,
    consume_user_token,
    create_session,
    issue_user_token,
    revoke_all_sessions,
    revoke_session,
    rotate_session,
    utcnow,
)
from app.services.mailer import deliver

logger = logging.getLogger("auth")
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

REFRESH_COOKIE = "avn_refresh"
LOGIN_FAILURE_LIMIT = 10
LOGIN_WINDOW_SECONDS = 15 * 60
FORGOT_LIMIT = 5
FORGOT_WINDOW_SECONDS = 60 * 60


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        httponly=True,
        secure=not settings.is_local,
        samesite="lax",
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


def _start_session(db: Session, user: User, request: Request, response: Response) -> AccessTokenOut:
    access, refresh = create_session(
        db, user, user_agent=request.headers.get("user-agent"), ip=audit.client_ip(request)
    )
    _set_refresh_cookie(response, refresh)
    return AccessTokenOut(access_token=access)


def _send_verification(db: Session, user: User) -> str:
    token = issue_user_token(db, user, "verify_email")
    link = f"{settings.frontend_base_url}/verify-email?token={token}"
    return deliver(user.email, "Verify your aVn email", f"Hi {user.name},\n\nConfirm your email address:\n{link}\n\nThis link expires in 48 hours.")


SIGNUP_WINDOW_SECONDS = 60 * 60


@router.post("/signup", response_model=SignupAcceptedOut, status_code=status.HTTP_202_ACCEPTED)
def signup(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    """Create a new workspace (tenant) owned by this user.

    The response never reveals whether the email was already registered: an existing account gets an
    email instead, and the caller sees the same "accepted" reply either way."""
    key = f"signup:{audit.client_ip(request)}"
    if ratelimit.is_limited(key, settings.signup_limit, SIGNUP_WINDOW_SECONDS):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many signups from this network. Try again later.")
    ratelimit.hit(key, SIGNUP_WINDOW_SECONDS)

    email = payload.email.lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        deliver(existing.email, "Someone tried to create an aVn account with your email",
                "\n".join([
                    f"Hi {existing.name},",
                    "",
                    "Someone tried to sign up for aVn with this email address. You already have an account.",
                    f"Sign in: {settings.frontend_base_url}/login",
                    f"Forgot your password? {settings.frontend_base_url}/forgot-password",
                    "",
                ]) +
                "If this wasn't you, you can ignore this email.")
        audit.record(db, action="signup_existing_email", entity="User", entity_id=existing.id,
                     tenant_id=existing.tenant_id, request=request)
        return SignupAcceptedOut()

    # Public signup always creates a fresh tenant with this user as its Owner.
    # Joining an existing tenant must go through an invitation, never a client-supplied id.
    company_name = (payload.company_name or "").strip() or f"{payload.name.strip()}'s Workspace"
    tenant = Tenant(name=company_name)
    db.add(tenant)
    db.flush()
    user = User(
        email=email,
        name=payload.name.strip(),
        hashed_password=get_password_hash(payload.password),
        role="Owner",
        status="active",
        tenant_id=tenant.id,
        joined=utcnow().strftime("%Y-%m-%d"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.record(db, action="signup", entity="User", entity_id=user.id, tenant_id=tenant.id, user_id=user.id, request=request)
    _send_verification(db, user)
    return SignupAcceptedOut()


@router.post("/login", response_model=AccessTokenOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower()
    limit_key = f"login:{audit.client_ip(request)}:{email}"
    if ratelimit.is_limited(limit_key, LOGIN_FAILURE_LIMIT, LOGIN_WINDOW_SECONDS):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts. Try again in 15 minutes.")

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        ratelimit.hit(limit_key, LOGIN_WINDOW_SECONDS)
        audit.record(db, action="login_failed", entity="User", entity_id=user.id if user else None,
                     tenant_id=user.tenant_id if user else None, details={"email": email}, request=request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    ratelimit.reset(limit_key)
    token = _start_session(db, user, request, response)
    audit.record(db, action="login", entity="User", entity_id=user.id, tenant_id=user.tenant_id, user_id=user.id, request=request)
    return token


@router.post("/refresh", response_model=AccessTokenOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    """Rotate the refresh cookie and return a new access token."""
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    try:
        _, access, new_refresh = rotate_session(db, refresh_token)
    except SessionError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    _set_refresh_cookie(response, new_refresh)
    return AccessTokenOut(access_token=access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    auth_header = request.headers.get("authorization", "")
    payload = decode_token(auth_header.removeprefix("Bearer ").strip()) or {}
    if payload.get("sid"):
        revoke_session(db, payload["sid"])
    _clear_refresh_cookie(response)
    audit.record(db, action="logout", entity="User", entity_id=current_user.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


def _current_sid(request: Request) -> str | None:
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return (decode_token(token) or {}).get("sid")


@router.get("/sessions", response_model=List[SessionOut])
def list_sessions(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The caller's signed-in devices."""
    now = utcnow()
    sid = _current_sid(request)
    rows = db.query(AuthSession).filter(
        AuthSession.user_id == current_user.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now
    ).order_by(AuthSession.last_used_at.desc()).all()
    return [SessionOut(id=r.id, user_agent=r.user_agent, ip=r.ip, created_at=r.created_at,
                       last_used_at=r.last_used_at, current=r.id == sid) for r in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def end_session(session_id: str, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sign one of the caller's devices out."""
    row = db.query(AuthSession).filter(AuthSession.id == session_id, AuthSession.user_id == current_user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    revoke_session(db, row.id)
    audit.record(db, action="session_revoked", entity="AuthSession", entity_id=row.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(payload: TokenIn, request: Request, db: Session = Depends(get_db)):
    user = consume_user_token(db, payload.token, "verify_email")
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This verification link is invalid or has expired.")
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        db.commit()
    audit.record(db, action="email_verified", entity="User", entity_id=user.id, tenant_id=user.tenant_id, user_id=user.id, request=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email/resend")
def resend_verification(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.email_verified_at is not None:
        return {"email_status": "already_verified"}
    return {"email_status": _send_verification(db, current_user)}


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: EmailIn, request: Request, db: Session = Depends(get_db)):
    """Always 202 so the response doesn't reveal whether an account exists."""
    key = f"forgot:{audit.client_ip(request)}"
    if ratelimit.is_limited(key, FORGOT_LIMIT, FORGOT_WINDOW_SECONDS):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests. Try again later.")
    ratelimit.hit(key, FORGOT_WINDOW_SECONDS)

    user = db.query(User).filter(User.email == payload.email.lower(), User.status == "active").first()
    if user:
        token = issue_user_token(db, user, "reset_password")
        link = f"{settings.frontend_base_url}/reset-password?token={token}"
        deliver(user.email, "Reset your aVn password",
              f"Hi {user.name},\n\nReset your password:\n{link}\n\nThis link expires in 1 hour. If you didn't ask for this, ignore this email.")
        audit.record(db, action="password_reset_requested", entity="User", entity_id=user.id, tenant_id=user.tenant_id, request=request)
    return {"status": "accepted"}


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordIn, request: Request, db: Session = Depends(get_db)):
    user = consume_user_token(db, payload.token, "reset_password")
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link is invalid or has expired.")
    user.hashed_password = get_password_hash(payload.password)
    # The link proves control of the mailbox.
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    db.commit()
    revoke_all_sessions(db, user.id)
    audit.record(db, action="password_reset", entity="User", entity_id=user.id, tenant_id=user.tenant_id, user_id=user.id, request=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _open_invitation(db: Session, token: str) -> Invitation:
    invitation = db.query(Invitation).filter(Invitation.token_hash == hash_token(token)).first()
    if (invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None
            or invitation.expires_at <= utcnow()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invitation is invalid or has expired.")
    return invitation


@router.get("/invitations/{token}", response_model=InvitationPreviewOut)
def preview_invitation(token: str, db: Session = Depends(get_db)):
    invitation = _open_invitation(db, token)
    tenant = db.query(Tenant).filter(Tenant.id == invitation.tenant_id).first()
    return InvitationPreviewOut(email=invitation.email, role=invitation.role,
                                tenant_name=tenant.name if tenant else "", expires_at=invitation.expires_at)


@router.post("/invitations/accept", response_model=AccessTokenOut)
def accept_invitation(payload: AcceptInvitationIn, request: Request, response: Response, db: Session = Depends(get_db)):
    invitation = _open_invitation(db, payload.token)
    if db.query(User).filter(User.email == invitation.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="An account with this email already exists. Each account belongs to one workspace for now.")
    now = utcnow()
    user = User(
        email=invitation.email,
        name=payload.name.strip(),
        hashed_password=get_password_hash(payload.password),
        role=invitation.role,
        status="active",
        tenant_id=invitation.tenant_id,
        joined=now.strftime("%Y-%m-%d"),
        email_verified_at=now,  # the invitation link was delivered to this address
    )
    db.add(user)
    invitation.accepted_at = now
    db.commit()
    db.refresh(user)
    audit.record(db, action="invitation_accepted", entity="Invitation", entity_id=invitation.id,
                 tenant_id=invitation.tenant_id, user_id=user.id, request=request)
    return _start_session(db, user, request, response)
