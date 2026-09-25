"""Lead-capture webhook: a secret URL per workspace that websites and other tools post leads to."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.auth_deps import RoleChecker
from app.core.database import get_db
from app.core.security import hash_token, new_opaque_token
from app.core.settings import settings
from app.models.lead import Lead, LeadActivity
from app.models.user import User
from app.models.workflow import WebhookEndpoint
from app.schemas.common import UTCDateTime
from app.schemas.lead import normalize_phone
from app.services import audit, webhooks, workflow_events

router = APIRouter(tags=["Webhooks"])
require_admin = RoleChecker(["Admin"])

HOOK_CALLS_PER_MINUTE = 60
MAX_BODY_BYTES = 64 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WebhookStatusOut(BaseModel):
    configured: bool
    created_at: Optional[UTCDateTime] = None
    last_used_at: Optional[UTCDateTime] = None


class WebhookCreatedOut(BaseModel):
    url: str
    signing_secret: str


class InboundLead(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=5000)
    custom_fields: Optional[Dict[str, Any]] = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


@router.get("/api/integrations/webhook", response_model=WebhookStatusOut)
def webhook_status(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    row = db.query(WebhookEndpoint).filter(WebhookEndpoint.tenant_id == current_user.tenant_id).first()
    return WebhookStatusOut(configured=row is not None, created_at=row.created_at if row else None,
                            last_used_at=row.last_used_at if row else None)


@router.post("/api/integrations/webhook/rotate", response_model=WebhookCreatedOut)
def rotate_webhook(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Create or replace the workspace's webhook URL and signing secret. Both are shown only now;
    the previous URL stops working immediately."""
    token, secret = new_opaque_token(), new_opaque_token()
    row = db.query(WebhookEndpoint).filter(WebhookEndpoint.tenant_id == current_user.tenant_id).first()
    if row is None:
        row = WebhookEndpoint(tenant_id=current_user.tenant_id, token_hash="", signing_secret="", created_at=_now())
        db.add(row)
    row.token_hash = hash_token(token)
    row.signing_secret = webhooks.seal_secret(secret)
    row.created_at = _now()
    row.last_used_at = None
    db.commit()
    audit.record(db, action="webhook_rotated", entity="WebhookEndpoint", entity_id=row.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    base = str(settings.public_api_url or request.base_url).rstrip("/")
    return WebhookCreatedOut(url=f"{base}/api/hooks/leads/{token}", signing_secret=secret)


@router.delete("/api/integrations/webhook", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    db.query(WebhookEndpoint).filter(WebhookEndpoint.tenant_id == current_user.tenant_id).delete()
    db.commit()
    audit.record(db, action="webhook_deleted", entity="WebhookEndpoint", tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/hooks/leads/{token}", status_code=status.HTTP_202_ACCEPTED, include_in_schema=False)
async def receive_lead(token: str, request: Request, db: Session = Depends(get_db)):
    """Public: create or update a lead. An unknown token gets the same 404 as a missing route."""
    row = db.query(WebhookEndpoint).filter(WebhookEndpoint.token_hash == hash_token(token)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Not Found")
    limit_key = f"hook:{row.id}"
    if ratelimit.is_limited(limit_key, HOOK_CALLS_PER_MINUTE, 60):
        raise HTTPException(status_code=429, detail="Too many requests")
    ratelimit.hit(limit_key, 60)
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Body too large")
    try:
        payload = InboundLead.model_validate_json(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise HTTPException(status_code=422, detail=f"{first['loc'][-1] if first['loc'] else 'body'}: {first['msg'].removeprefix('Value error, ')}")

    from app.services.lead_fields import FieldValueError, merge_values
    tenant_id = row.tenant_id
    lead = db.query(Lead).filter(Lead.tenant_id == tenant_id, Lead.phone == payload.phone, Lead.deleted_at == None).first()
    created = lead is None
    try:
        if created:
            lead = Lead(tenant_id=tenant_id, name=payload.name.strip(), phone=payload.phone, email=payload.email,
                        company=payload.company, notes=payload.notes, status="New", score="Cold",
                        custom_fields=merge_values(db, tenant_id, None, payload.custom_fields) or None)
            db.add(lead)
        else:
            # An existing lead only gains information; the form never erases what the team entered.
            lead.email = lead.email or payload.email
            lead.company = lead.company or payload.company
            if payload.notes:
                lead.notes = f"{lead.notes}\n\n{payload.notes}".strip() if lead.notes else payload.notes
            lead.custom_fields = merge_values(db, tenant_id, lead.custom_fields, payload.custom_fields) or None
    except FieldValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    db.flush()
    db.add(LeadActivity(lead_id=lead.id, tenant_id=tenant_id, activity_type="crm_update",
                        title="Lead captured by webhook" if created else "Lead updated by webhook",
                        description=f"Received from {request.headers.get('origin') or 'an external source'}."))
    row.last_used_at = _now()
    db.commit()
    if created:
        workflow_events.emit(db, tenant_id, "lead_created", lead_id=lead.id)
    workflow_events.emit(db, tenant_id, "webhook_received", lead_id=lead.id)
    return {"status": "accepted", "lead_id": lead.id, "created": created}
