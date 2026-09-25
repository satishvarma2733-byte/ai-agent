from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import random

from app.core.database import get_db
from app.models.call import CallLog
from app.schemas.call import CallLogOut, CallLogCreate, LiveCallsOut
from outbound_calls import dispatch_outbound_call
from app.core import ratelimit
from app.core.auth_deps import RoleChecker, get_current_user
from app.services import audit, call_control
from app.models.user import User

router = APIRouter(tags=["Call Management"])

SINGLE_CALLS_PER_HOUR = 30
MAX_BULK_NUMBERS = 100

@router.post("/api/call/single")
async def call_single(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Dispatch a single outbound call via LiveKit WebRTC channel."""
    data = await request.json()
    phone = str(data.get("phone") or data.get("phone_number") or "").strip()
    caller_name = str(data.get("caller_name") or "").strip()
    if not phone:
        raise HTTPException(status_code=422, detail="phone is required")
    # Every dial costs money and reaches a real person: cap it per user.
    limit_key = f"dial:{current_user.id}"
    if ratelimit.is_limited(limit_key, SINGLE_CALLS_PER_HOUR, 3600):
        raise HTTPException(status_code=429, detail=f"Call limit reached ({SINGLE_CALLS_PER_HOUR} per hour). Try again later or use a campaign.")
    ratelimit.hit(limit_key, 3600)
    
    # Load config defaults
    from app.core.runtime_config import load_runtime_config as _load_runtime_config
    config = _load_runtime_config()
    
    try:
        result = await dispatch_outbound_call(
            phone,
            config=config,
            caller_name=caller_name,
            extra_metadata={"tenant_id": current_user.tenant_id}
        )
        
        # Save a placeholder log row
        log = CallLog(
            phone_number=phone,
            caller_name=caller_name,
            direction="outbound",
            call_room_id=result.get("room"),
            tenant_id=current_user.tenant_id
        )
        db.add(log)
        db.commit()
        audit.record(db, action="call_dispatched", entity="CallLog", entity_id=log.id, tenant_id=current_user.tenant_id,
                     user_id=current_user.id, details={"room": result.get("room")}, request=request)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/api/call/bulk")
async def call_bulk(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Manager"]))
):
    """Dispatch calls to several numbers at once (Manager or higher, up to MAX_BULK_NUMBERS)."""
    data = await request.json()
    raw_numbers = data.get("numbers") or data.get("phone_numbers") or ""
    
    if isinstance(raw_numbers, list):
        numbers = [str(item).strip() for item in raw_numbers if str(item).strip()]
    else:
        numbers = [item.strip() for item in str(raw_numbers).splitlines() if item.strip()]
        
    if len(numbers) > MAX_BULK_NUMBERS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_BULK_NUMBERS} numbers per request; use a campaign for more.")
    audit.record(db, action="bulk_calls_requested", entity="CallLog", tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"count": len(numbers)}, request=request)
    results = []
    from app.core.runtime_config import load_runtime_config as _load_runtime_config
    config = _load_runtime_config()
    
    for phone in numbers:
        try:
            result = await dispatch_outbound_call(
                phone,
                config=config,
                extra_metadata={"tenant_id": current_user.tenant_id}
            )
            results.append({
                "phone": phone,
                "status": "ok",
                "dispatch_id": result["dispatch_id"],
                "room": result["room"]
            })
            # Insert log
            log = CallLog(
                phone_number=phone,
                direction="outbound",
                    call_room_id=result.get("room"),
                tenant_id=current_user.tenant_id
            )
            db.add(log)
        except Exception as exc:
            results.append({
                "phone": phone,
                "status": "error",
                "message": str(exc)
            })
    db.commit()
    return {"results": results, "total": len(results)}

@router.get("/api/outbound", response_model=List[CallLogOut])
def get_outbound_calls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch active outbound calls from logs."""
    return db.query(CallLog).filter(
        CallLog.direction == "outbound",
        CallLog.tenant_id == current_user.tenant_id
    ).order_by(CallLog.created_at.desc()).all()

@router.get("/api/calls/live", response_model=LiveCallsOut)
async def get_live_calls(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Calls in progress right now, read from LiveKit."""
    from app.core.runtime_config import load_runtime_config as _load_runtime_config
    return await call_control.live_calls(db, current_user.tenant_id, _load_runtime_config())

@router.post("/api/outbound/end")
async def end_outbound_call(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """End a live outbound call by closing its LiveKit room."""
    from app.core.runtime_config import load_runtime_config as _load_runtime_config
    call = call_control.find_call(db, current_user.tenant_id, payload)
    await call_control.end_call(call, _load_runtime_config())
    audit.record(db, action="call_ended", entity="CallLog", entity_id=call.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"room": call.call_room_id}, request=request)
    return {"status": "ok", "room": call.call_room_id}

@router.post("/api/outbound/transfer", status_code=501)
def transfer_outbound_call(payload: dict, current_user: User = Depends(get_current_user)):
    """Not available yet: transfers happen inside the voice agent."""
    raise call_control.not_available("Transferring a call from the dashboard")

@router.post("/api/outbound/voicemail", status_code=501)
def voicemail_outbound_call(payload: dict, current_user: User = Depends(get_current_user)):
    """Not available yet."""
    raise call_control.not_available("Sending a caller to voicemail")

@router.get("/api/logs", response_model=List[CallLogOut])
def get_call_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve call details including metrics and summaries."""
    return db.query(CallLog).filter(
        CallLog.tenant_id == current_user.tenant_id
    ).order_by(CallLog.created_at.desc()).limit(100).all()

@router.get("/api/logs/{log_id}/transcript")
def get_call_transcript(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch full textual transcript of the call."""
    log = db.query(CallLog).filter(
        CallLog.id == log_id,
        CallLog.tenant_id == current_user.tenant_id
    ).first()
    if not log:
        raise HTTPException(status_code=404, detail="Transcript log not found")
        
    text = f"Call Log - {log.created_at}\n"
    text += f"Phone: {log.phone_number}\n"
    text += f"Duration: {log.duration_seconds}s\n"
    text += f"Summary: {log.summary}\n\n"
    text += "--- TRANSCRIPT ---\n"
    text += log.transcript or "No transcript available."
    
    return PlainTextResponse(
        content=text,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=transcript_{log_id}.txt"}
    )
