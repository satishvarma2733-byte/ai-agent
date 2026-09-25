from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.call import CallLog
from app.schemas.call import CallLogOut
from app.core.auth_deps import get_current_user
from app.models.user import User
from app.services import audit, call_control

router = APIRouter(tags=["Inbound Management"])

@router.get("/api/inbound", response_model=List[CallLogOut])
def get_inbound_calls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve active inbound calls from logs."""
    return db.query(CallLog).filter(
        CallLog.direction == "inbound",
        CallLog.tenant_id == current_user.tenant_id
    ).order_by(CallLog.created_at.desc()).all()

@router.post("/api/inbound/start", status_code=501)
def start_inbound_call(payload: dict, current_user: User = Depends(get_current_user)):
    """Inbound calls start when someone dials the agent's number; they cannot be started from here."""
    raise call_control.not_available("Starting an inbound call from the dashboard")

@router.post("/api/inbound/end")
async def end_inbound_call(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """End a live inbound call by closing its LiveKit room."""
    from app.core.runtime_config import load_runtime_config as _load_runtime_config
    call = call_control.find_call(db, current_user.tenant_id, payload)
    await call_control.end_call(call, _load_runtime_config())
    audit.record(db, action="call_ended", entity="CallLog", entity_id=call.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"room": call.call_room_id}, request=request)
    return {"status": "ok", "room": call.call_room_id}

@router.post("/api/inbound/transfer", status_code=501)
def transfer_inbound_call(payload: dict, current_user: User = Depends(get_current_user)):
    """Not available yet: transfers happen inside the voice agent."""
    raise call_control.not_available("Transferring a call from the dashboard")

@router.post("/api/inbound/voicemail", status_code=501)
def voicemail_inbound_call(payload: dict, current_user: User = Depends(get_current_user)):
    """Not available yet."""
    raise call_control.not_available("Sending a caller to voicemail")
