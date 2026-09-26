"""SMS through the workspace's own Twilio account: connect, send, and the "Send SMS" workflow step."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import config_crypto
from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.models.lead import Lead
from app.models.sms import SmsAccount
from app.models.user import User
from app.services import audit, sms

router = APIRouter(tags=["SMS"])


class SmsStatusOut(BaseModel):
    connected: bool
    provider: Optional[str] = None
    sender: Optional[str] = None


class SmsConnectIn(BaseModel):
    account_sid: str
    auth_token: str
    from_number: str


class SmsSendIn(BaseModel):
    phone: Optional[str] = None
    lead_id: Optional[str] = None
    text: str = Field(min_length=1, max_length=sms.MAX_CHARS)


class SmsSentOut(BaseModel):
    status: str
    sid: str


def _status(account: SmsAccount | None) -> SmsStatusOut:
    return SmsStatusOut(connected=False) if account is None else SmsStatusOut(connected=True, provider=account.provider,
                                                                               sender=account.sender)


@router.get("/api/integrations/sms", response_model=SmsStatusOut)
def sms_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _status(db.query(SmsAccount).filter(SmsAccount.tenant_id == current_user.tenant_id).first())


@router.put("/api/integrations/sms", response_model=SmsStatusOut)
def connect_sms(payload: SmsConnectIn, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(RoleChecker(["Admin"]))):
    """Check the Twilio details, then store them encrypted. Replaces any existing SMS sender."""
    try:
        sms.ensure_can_store_credentials()
    except config_crypto.SecretsKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    try:
        account = sms.save_account(db, current_user.tenant_id, current_user.id, payload.account_sid, payload.auth_token,
                                   payload.from_number)
    except sms.SmsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.record(db, action="sms_connected", entity="SmsAccount", entity_id=account.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"sender": account.sender}, request=request)
    return _status(account)


@router.delete("/api/integrations/sms", status_code=204)
def disconnect_sms(request: Request, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin"]))):
    if not db.query(SmsAccount).filter(SmsAccount.tenant_id == current_user.tenant_id).delete():
        raise HTTPException(status_code=404, detail="SMS isn't connected.")
    db.commit()
    audit.record(db, action="sms_disconnected", entity="SmsAccount", tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return Response(status_code=204)


@router.post("/api/crm/sms", response_model=SmsSentOut)
def send_sms(payload: SmsSendIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = None
    if payload.lead_id:
        lead = db.query(Lead).filter(Lead.id == payload.lead_id, Lead.tenant_id == current_user.tenant_id,
                                     Lead.deleted_at == None).first()  # noqa: E711
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
    phone = payload.phone or (lead.phone if lead else None)
    if not phone:
        raise HTTPException(status_code=422, detail="Give a phone number or a lead.")
    try:
        sid = sms.send(db, current_user.tenant_id, phone, payload.text, lead=lead)
    except sms.SmsNotConnected as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except sms.SmsError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return SmsSentOut(status="sent", sid=sid)
