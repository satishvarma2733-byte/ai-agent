"""The signed-in user's workspace (tenant) profile."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.services import audit

router = APIRouter(prefix="/api/workspace", tags=["Workspace"])


class WorkspaceOut(BaseModel):
    id: str
    name: str
    plan: str
    status: str


class WorkspaceUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


def _tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return tenant


@router.get("", response_model=WorkspaceOut)
def get_workspace(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _tenant(db, current_user.tenant_id)


@router.patch("", response_model=WorkspaceOut)
def update_workspace(payload: WorkspaceUpdate, request: Request, db: Session = Depends(get_db),
                     current_user: User = Depends(RoleChecker(["Admin"]))):
    tenant = _tenant(db, current_user.tenant_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Workspace name is required")
    tenant.name = name
    db.commit()
    audit.record(db, action="workspace_renamed", entity="Tenant", entity_id=tenant.id, tenant_id=tenant.id,
                 user_id=current_user.id, details={"name": name}, request=request)
    return tenant


class CallSummarySettingsIO(BaseModel):
    enabled: bool = False
    to_managers: bool = True
    to_assignee: bool = True
    emails: list[str] = Field(default_factory=list, max_length=20)
    min_seconds: int = Field(default=15, ge=0, le=600)
    include_transcript: bool = False
    timezone: str = Field(default="Asia/Kolkata", max_length=64)


class CallSummarySettingsOut(CallSummarySettingsIO):
    # False until the server has an email provider (RESEND_API_KEY and EMAIL_FROM); summaries can't be delivered before then.
    email_ready: bool


class CallSummaryTestOut(BaseModel):
    recipients: list[str]
    status: str


def _summary_settings_out(cfg) -> CallSummarySettingsOut:
    from app.core.settings import settings
    return CallSummarySettingsOut(**{k: getattr(cfg, k) for k in CallSummarySettingsIO.model_fields},
                                  email_ready=settings.email_configured or settings.is_local)


@router.get("/call-summaries", response_model=CallSummarySettingsOut)
def get_call_summaries(db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin"]))):
    """Who gets an email after each call."""
    from app.services import call_summaries
    return _summary_settings_out(call_summaries.read_settings(_tenant(db, current_user.tenant_id)))


@router.put("/call-summaries", response_model=CallSummarySettingsOut)
def update_call_summaries(payload: CallSummarySettingsIO, request: Request, db: Session = Depends(get_db),
                          current_user: User = Depends(RoleChecker(["Admin"]))):
    from app.services import call_summaries
    tenant = _tenant(db, current_user.tenant_id)
    try:
        cfg = call_summaries.save_settings(db, tenant, call_summaries.SummarySettings(**payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit.record(db, action="call_summaries_updated", entity="Tenant", entity_id=tenant.id, tenant_id=tenant.id,
                 user_id=current_user.id, details={"enabled": cfg.enabled, "extra_emails": len(cfg.emails)}, request=request)
    return _summary_settings_out(cfg)


@router.post("/call-summaries/test", response_model=CallSummaryTestOut)
def test_call_summary(db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin"]))):
    """Email the latest finished call's summary to the configured recipients now (the call keeps its own status)."""
    from app.models.call import CallLog
    from app.services import call_summaries
    from app.services.mailer import deliver
    cfg = call_summaries.read_settings(_tenant(db, current_user.tenant_id))
    log = db.query(CallLog).filter(CallLog.tenant_id == current_user.tenant_id, CallLog.duration_seconds > 0).order_by(
        CallLog.created_at.desc()).first()
    if log is None:
        raise HTTPException(status_code=409, detail="There are no finished calls to summarise yet.")
    to = call_summaries.recipients(db, current_user.tenant_id, cfg, log.phone_number)
    if not to:
        raise HTTPException(status_code=409, detail="No one would receive summaries. Choose at least one recipient.")
    subject, body = call_summaries.compose(db, log, cfg)
    outcomes = [deliver(address, f"[Test] {subject}", body) for address in to]
    return CallSummaryTestOut(recipients=to, status=next((s for s in ("sent", "logged") if s in outcomes), outcomes[0]))
