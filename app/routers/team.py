from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.core.permissions import ASSIGNABLE_ROLES, rank
from app.core.security import hash_token, new_opaque_token
from app.core.settings import settings
from app.models.auth import Invitation
from app.models.tenant import Tenant
from app.models.user import User
from app.services.mailer import deliver
from app.schemas.auth import InvitationCreate, InvitationCreatedOut, InvitationOut, MemberOut, MemberUpdate, OwnershipTransferIn
from app.services import audit
from app.services.auth_service import INVITATION_TTL, revoke_all_sessions, utcnow

router = APIRouter(prefix="/api/team", tags=["Team"])

require_admin = RoleChecker(["Admin"])


def _member_out(user: User) -> MemberOut:
    return MemberOut(
        id=user.id, name=user.name, email=user.email, role=user.role, status=user.status,
        phone=user.phone, joined=user.joined, last_seen=user.last_seen,
        email_verified=user.email_verified_at is not None,
    )


def _invitation_out(inv: Invitation) -> InvitationOut:
    return InvitationOut(id=inv.id, email=inv.email, role=inv.role, created_at=inv.created_at, expires_at=inv.expires_at)


@router.get("/members", response_model=List[MemberOut])
def list_members(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    users = db.query(User).filter(User.tenant_id == current_user.tenant_id).order_by(User.created_at).all()
    return [_member_out(u) for u in users]


@router.patch("/members/{user_id}", response_model=MemberOut)
def update_member(
    user_id: str,
    payload: MemberUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    member = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't change your own role or status.")
    if member.role == "Owner":
        raise HTTPException(status_code=403, detail="The workspace owner can't be changed.")
    if rank(member.role) > rank(current_user.role):
        raise HTTPException(status_code=403, detail="You can't change someone with a higher role than yours.")

    changes: dict[str, dict[str, str]] = {}
    if payload.role is not None and payload.role != member.role:
        if payload.role not in ASSIGNABLE_ROLES:
            raise HTTPException(status_code=422, detail=f"Role must be one of: {', '.join(ASSIGNABLE_ROLES)}")
        if rank(payload.role) > rank(current_user.role):
            raise HTTPException(status_code=403, detail="You can't grant a role higher than your own.")
        changes["role"] = {"from": member.role, "to": payload.role}
        member.role = payload.role
    if payload.status is not None and payload.status != member.status:
        changes["status"] = {"from": member.status, "to": payload.status}
        member.status = payload.status
    db.commit()
    if changes.get("status", {}).get("to") == "inactive" or "role" in changes:
        # Access tokens carry the role; force a fresh sign-in so old privileges end now.
        revoke_all_sessions(db, member.id)
    if changes:
        audit.record(db, action="member_updated", entity="User", entity_id=member.id,
                     tenant_id=current_user.tenant_id, user_id=current_user.id, details=changes, request=request)
    return _member_out(member)


def _detach_user(db: Session, user_id: str) -> None:
    """Clear references to a user before deleting them. Postgres applies the FK rules itself, but
    SQLite (local development) doesn't enforce foreign keys, so this is done explicitly."""
    from app.models.agent import Agent, AgentChange, AgentLifecycleEvent, AgentVersion
    from app.models.auth import AuthSession, AuthToken
    from app.models.lead import Lead
    for model, columns in ((Agent, ("created_by",)), (AgentVersion, ("created_by", "approved_by")),
                           (AgentChange, ("user_id",)), (AgentLifecycleEvent, ("user_id",)),
                           (Invitation, ("invited_by",)), (Lead, ("assigned_user_id",))):
        for column in columns:
            db.query(model).filter(getattr(model, column) == user_id).update({column: None}, synchronize_session=False)
    db.query(AuthSession).filter(AuthSession.user_id == user_id).delete(synchronize_session=False)
    db.query(AuthToken).filter(AuthToken.user_id == user_id).delete(synchronize_session=False)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Remove someone from the workspace. Their leads become unassigned; their history stays (without their name)."""
    member = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't remove yourself.")
    if member.role == "Owner":
        raise HTTPException(status_code=403, detail="The workspace owner can't be removed. Transfer ownership first.")
    if rank(member.role) > rank(current_user.role):
        raise HTTPException(status_code=403, detail="You can't remove someone with a higher role than yours.")
    details = {"email": member.email, "role": member.role}
    _detach_user(db, member.id)
    db.delete(member)
    db.commit()
    audit.record(db, action="member_removed", entity="User", entity_id=user_id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details=details, request=request)


@router.post("/transfer-ownership", response_model=MemberOut)
def transfer_ownership(
    payload: OwnershipTransferIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Owner"])),
):
    """Make another active member the Owner; the current Owner becomes an Admin."""
    member = db.query(User).filter(User.id == payload.user_id, User.tenant_id == current_user.tenant_id).first()
    if member is None or member.id == current_user.id:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.status != "active":
        raise HTTPException(status_code=400, detail="Ownership can only go to an active member.")
    previous_role = member.role
    member.role = "Owner"
    current_user.role = "Admin"
    db.commit()
    revoke_all_sessions(db, member.id)  # their next sign-in carries the new role
    audit.record(db, action="ownership_transferred", entity="User", entity_id=member.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"from_user": current_user.id, "previous_role": previous_role}, request=request)
    return _member_out(member)


@router.get("/invitations", response_model=List[InvitationOut])
def list_invitations(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = db.query(Invitation).filter(
        Invitation.tenant_id == current_user.tenant_id,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
        Invitation.expires_at > utcnow(),
    ).order_by(Invitation.created_at.desc()).all()
    return [_invitation_out(r) for r in rows]


@router.post("/invitations", response_model=InvitationCreatedOut, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    email = payload.email.lower()
    if payload.role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of: {', '.join(ASSIGNABLE_ROLES)}")
    if rank(payload.role) > rank(current_user.role):
        raise HTTPException(status_code=403, detail="You can't invite someone with a role higher than your own.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="This email already has an aVn account.")

    now = utcnow()
    # Re-inviting replaces any pending invitation for the same address.
    db.query(Invitation).filter(
        Invitation.tenant_id == current_user.tenant_id, Invitation.email == email,
        Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None),
    ).update({Invitation.revoked_at: now}, synchronize_session=False)

    token = new_opaque_token()
    invitation = Invitation(
        tenant_id=current_user.tenant_id, email=email, role=payload.role, token_hash=hash_token(token),
        invited_by=current_user.id, created_at=now, expires_at=now + INVITATION_TTL,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    accept_url = f"{settings.frontend_base_url}/accept-invite?token={token}"
    email_status = deliver(
        email,
        f"{current_user.name} invited you to {tenant.name if tenant else 'aVn'}",
        f"{current_user.name} invited you to join {tenant.name if tenant else 'their workspace'} on aVn as {payload.role}.\n\n"
        f"Accept the invitation:\n{accept_url}\n\nThis link expires in {INVITATION_TTL.days} days.",
    )
    audit.record(db, action="invitation_created", entity="Invitation", entity_id=invitation.id,
                 tenant_id=current_user.tenant_id, user_id=current_user.id,
                 details={"email": email, "role": payload.role, "email_status": email_status}, request=request)
    return InvitationCreatedOut(invitation=_invitation_out(invitation), accept_url=accept_url, email_status=email_status)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    invitation = db.query(Invitation).filter(
        Invitation.id == invitation_id, Invitation.tenant_id == current_user.tenant_id
    ).first()
    if invitation is None or invitation.accepted_at is not None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.revoked_at is None:
        invitation.revoked_at = utcnow()
        db.commit()
        audit.record(db, action="invitation_revoked", entity="Invitation", entity_id=invitation.id,
                     tenant_id=current_user.tenant_id, user_id=current_user.id, request=request)
