"""WhatsApp: connecting a workspace's sender, sending, the message log and provider webhooks."""
import json
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import config_crypto
from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.core.settings import settings
from app.core.tenancy import bind_session_to_tenant
from app.models.lead import Lead
from app.models.user import User
from app.models.whatsapp import WhatsAppAccount, WhatsAppMessage
from app.schemas.common import UTCDateTime
from app.services import audit, whatsapp

router = APIRouter(tags=["WhatsApp"])

MAX_WEBHOOK_BYTES = 256 * 1024


class WhatsAppStatusOut(BaseModel):
    connected: bool
    provider: Optional[str] = None
    sender: Optional[str] = None
    status: Optional[str] = None
    last_error: Optional[str] = None
    # Admins only: where to point the provider's webhooks, and Meta's verify token.
    webhook_url: Optional[str] = None
    verify_token: Optional[str] = None


class WhatsAppConnectIn(BaseModel):
    provider: Literal["meta", "twilio"]
    phone_number_id: Optional[str] = None
    access_token: Optional[str] = None
    app_secret: Optional[str] = None
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    from_number: Optional[str] = None


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    language: str = Field(default="en", max_length=20)
    params: List[str] = Field(default_factory=list, max_length=20)


class WhatsAppSendIn(BaseModel):
    phone: Optional[str] = None
    lead_id: Optional[str] = None
    text: Optional[str] = Field(default=None, max_length=4096)
    template: Optional[TemplateIn] = None


class WhatsAppMessageOut(BaseModel):
    id: str
    lead_id: Optional[str] = None
    phone: str
    direction: str
    body: Optional[str] = None
    template: Optional[str] = None
    status: str
    error: Optional[str] = None
    source: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True


def _account(db: Session, tenant_id: str) -> WhatsAppAccount | None:
    return db.query(WhatsAppAccount).filter(WhatsAppAccount.tenant_id == tenant_id).first()


def _status(account: WhatsAppAccount | None, user: User, request: Request) -> WhatsAppStatusOut:
    if account is None:
        return WhatsAppStatusOut(connected=False)
    out = WhatsAppStatusOut(connected=True, provider=account.provider, sender=account.sender, status=account.status,
                            last_error=account.last_error)
    from app.core.permissions import at_least
    if at_least(user.role, "Admin"):
        out.webhook_url = whatsapp.webhook_url(account, str(request.base_url))
        if account.provider == "meta":
            out.verify_token = whatsapp.webhook_token(account)
    return out


@router.get("/api/integrations/whatsapp", response_model=WhatsAppStatusOut)
def whatsapp_status(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _status(_account(db, current_user.tenant_id), current_user, request)


@router.put("/api/integrations/whatsapp", response_model=WhatsAppStatusOut)
def connect_whatsapp(payload: WhatsAppConnectIn, request: Request, db: Session = Depends(get_db),
                     current_user: User = Depends(RoleChecker(["Admin"]))):
    """Check the credentials with the provider, then store them encrypted. Replaces any existing sender."""
    try:
        whatsapp.ensure_can_store_credentials()
    except config_crypto.SecretsKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    try:
        account = whatsapp.save_account(db, current_user.tenant_id, current_user.id, payload.provider,
                                        payload.model_dump(exclude={"provider"}))
    except whatsapp.WhatsAppError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.record(db, action="whatsapp_connected", entity="WhatsAppAccount", entity_id=account.id,
                 tenant_id=current_user.tenant_id, user_id=current_user.id,
                 details={"provider": account.provider, "sender": account.sender}, request=request)
    return _status(account, current_user, request)


@router.delete("/api/integrations/whatsapp", status_code=204)
def disconnect_whatsapp(request: Request, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin"]))):
    account = _account(db, current_user.tenant_id)
    if account is None:
        raise HTTPException(status_code=404, detail="WhatsApp isn't connected.")
    db.delete(account)
    db.commit()
    audit.record(db, action="whatsapp_disconnected", entity="WhatsAppAccount", tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return Response(status_code=204)


@router.post("/api/crm/whatsapp", response_model=WhatsAppMessageOut)
def send_whatsapp(payload: WhatsAppSendIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Send free text (within 24 hours of the customer's last message) or an approved template to a lead or number."""
    lead = None
    if payload.lead_id:
        lead = db.query(Lead).filter(Lead.id == payload.lead_id, Lead.tenant_id == current_user.tenant_id,
                                     Lead.deleted_at == None).first()  # noqa: E711
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
    phone = payload.phone or (lead.phone if lead else None)
    if not phone:
        raise HTTPException(status_code=422, detail="Give a phone number or a lead.")
    if not payload.text and not payload.template:
        raise HTTPException(status_code=422, detail="Write a message or choose a template.")
    template = whatsapp.Template(payload.template.name, payload.template.language, tuple(payload.template.params)) if payload.template else None
    try:
        return whatsapp.send(db, current_user.tenant_id, phone, text=payload.text, template=template, lead=lead, source="manual")
    except whatsapp.WhatsAppNotConnected as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except whatsapp.WhatsAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/api/whatsapp/messages", response_model=List[WhatsAppMessageOut])
def list_messages(lead_id: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(WhatsAppMessage).filter(WhatsAppMessage.tenant_id == current_user.tenant_id)
    if lead_id:
        query = query.filter(WhatsAppMessage.lead_id == lead_id)
    return query.order_by(WhatsAppMessage.created_at.desc()).limit(limit).all()


# --- Provider webhooks (public; the secret token in the URL picks the workspace) -----------------

def _hook_account(db: Session, provider: str, token: str) -> WhatsAppAccount:
    account = whatsapp.account_for_token(db, provider, token)
    if account is None:
        raise HTTPException(status_code=404, detail="Not Found")
    bind_session_to_tenant(db, account.tenant_id)
    return account


@router.get("/api/whatsapp/webhook/meta/{token}", include_in_schema=False)
def meta_verify(token: str, request: Request, db: Session = Depends(get_db)):
    """Meta's one-time subscription check: echo the challenge when the verify token matches."""
    _hook_account(db, "meta", token)
    q = request.query_params
    if q.get("hub.mode") != "subscribe" or q.get("hub.verify_token") != token:
        raise HTTPException(status_code=403, detail="Verify token mismatch")
    return Response(content=q.get("hub.challenge", ""), media_type="text/plain")


@router.post("/api/whatsapp/webhook/meta/{token}", include_in_schema=False)
async def meta_webhook(token: str, request: Request, db: Session = Depends(get_db)):
    account = _hook_account(db, "meta", token)
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Body too large")
    if not whatsapp.meta_signature_ok(account, raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=401, detail="Bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    whatsapp.handle_meta(db, account, payload)
    return {"status": "ok"}


@router.post("/api/whatsapp/webhook/twilio/{token}", include_in_schema=False)
async def twilio_webhook(token: str, request: Request, db: Session = Depends(get_db)):
    account = _hook_account(db, "twilio", token)
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Body too large")
    params = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    # Twilio signs the URL it called; behind a proxy that's the public URL, not the one this server sees.
    url = f"{settings.public_api_url.rstrip('/')}{request.url.path}" if settings.public_api_url else str(request.url)
    if not whatsapp.twilio_signature_ok(account, url, params, request.headers.get("x-twilio-signature")):
        raise HTTPException(status_code=401, detail="Bad signature")
    whatsapp.handle_twilio(db, account, params)
    # An empty TwiML reply: no automatic answer to the customer.
    return Response(content="<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>", media_type="application/xml")
