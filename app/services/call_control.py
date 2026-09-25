"""Actions on live calls. Each call runs in its own LiveKit room, so ending the room ends the call."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from livekit import api
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.call import CallLog
from outbound_calls import get_livekit_settings

NOT_AVAILABLE = "{action} is not available yet. The voice agent can transfer a caller itself when its transfer tool is configured."


def find_call(db: Session, tenant_id: str, payload: dict) -> CallLog:
    """The caller's own call, addressed by call-log id or LiveKit room name."""
    key = str(payload.get("id") or payload.get("room") or "").strip()
    if not key:
        raise HTTPException(status_code=422, detail="id is required")
    call = db.query(CallLog).filter(
        CallLog.tenant_id == tenant_id,
        or_(CallLog.id == key, CallLog.call_room_id == key),
    ).first()
    if call is None or not call.call_room_id:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


# Rooms older than this are not looked up; no call lasts that long.
LIVE_LOOKBACK = timedelta(hours=6)


def _client(config: dict) -> api.LiveKitAPI | None:
    settings = get_livekit_settings(config)
    if not (settings["url"] and settings["api_key"] and settings["api_secret"]):
        return None
    return api.LiveKitAPI(url=settings["url"], api_key=settings["api_key"], api_secret=settings["api_secret"])


async def live_calls(db: Session, tenant_id: str, config: dict) -> dict:
    """The tenant's calls whose LiveKit room is still open. `configured` is False without LiveKit settings."""
    since = (datetime.now(timezone.utc) - LIVE_LOOKBACK).replace(tzinfo=None)
    calls = {c.call_room_id: c for c in db.query(CallLog).filter(
        CallLog.tenant_id == tenant_id, CallLog.call_room_id.isnot(None), CallLog.created_at >= since)}
    lk = _client(config)
    if lk is None:
        return {"configured": False, "calls": []}
    if not calls:
        await lk.aclose()
        return {"configured": True, "calls": []}
    try:
        rooms = (await lk.room.list_rooms(api.ListRoomsRequest(names=list(calls)))).rooms
    except api.TwirpError as exc:
        raise HTTPException(status_code=502, detail=f"LiveKit did not answer: {exc.message}")
    finally:
        await lk.aclose()
    live = []
    for room in rooms:
        call = calls.get(room.name)
        if call is None or room.num_participants == 0:
            continue
        live.append({
            "id": call.id, "room": room.name, "phone_number": call.phone_number, "caller_name": call.caller_name,
            "direction": call.direction, "agent_id": call.agent_id, "participants": room.num_participants,
            "started_at": datetime.fromtimestamp(room.creation_time, timezone.utc) if room.creation_time else call.created_at.replace(tzinfo=timezone.utc),
        })
    live.sort(key=lambda item: item["started_at"], reverse=True)
    return {"configured": True, "calls": live}


async def end_call(call: CallLog, config: dict) -> None:
    lk = _client(config)
    if lk is None:
        raise HTTPException(status_code=503, detail="LiveKit is not configured, so calls cannot be controlled.")
    try:
        await lk.room.delete_room(api.DeleteRoomRequest(room=call.call_room_id))
    except api.TwirpError as exc:
        if exc.code == "not_found":
            raise HTTPException(status_code=409, detail="This call has already ended.")
        raise HTTPException(status_code=502, detail=f"LiveKit refused to end the call: {exc.message}")
    finally:
        await lk.aclose()


def not_available(action: str) -> HTTPException:
    return HTTPException(status_code=501, detail=NOT_AVAILABLE.format(action=action))
