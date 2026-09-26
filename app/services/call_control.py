"""Actions on live calls. Each call runs in its own LiveKit room, so ending the room ends the call."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from livekit import api
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.call import CallLog
from outbound_calls import get_livekit_settings

NOT_AVAILABLE = "{action} is not available yet. The voice agent can transfer a caller itself when its transfer tool is configured."
# Data messages on this topic are commands for the voice worker in the room (see agent_backend.py).
CONTROL_TOPIC = "avn.control"
LISTEN_TTL = timedelta(hours=1)
MAX_VOICEMAIL_CHARS = 600
DEFAULT_VOICEMAIL = ("Sorry we missed you. This is a message from our team; we'll call you back soon. "
                     "You can also call us back at any time. Thank you.")


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


def _require(config: dict) -> api.LiveKitAPI:
    lk = _client(config)
    if lk is None:
        raise HTTPException(status_code=503, detail="LiveKit is not configured, so calls cannot be controlled.")
    return lk


def transfer_destination(number: str | None, config: dict) -> str:
    """SIP URI for a phone number: through the Vobiz SIP domain when set, else a tel: URI for the trunk."""
    from app.schemas.lead import normalize_phone
    raw = (number or config.get("default_transfer_number") or os.getenv("DEFAULT_TRANSFER_NUMBER", "")).strip()
    if not raw:
        raise HTTPException(status_code=422, detail="Enter the number to transfer to (no default transfer number is set).")
    try:
        phone = normalize_phone(raw.replace("tel:", "").replace("sip:", ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    domain = str(config.get("vobiz_sip_domain") or os.getenv("VOBIZ_SIP_DOMAIN", "")).strip()
    return f"sip:{phone}@{domain}" if domain else f"tel:{phone}"


async def transfer_call(call: CallLog, config: dict, to: str | None) -> str:
    """Hand the caller's phone leg to another number (SIP REFER). The AI leaves the call."""
    destination = transfer_destination(to, config)
    lk = _require(config)
    try:
        participants = (await lk.room.list_participants(api.ListParticipantsRequest(room=call.call_room_id))).participants
        caller = next((p for p in participants if p.kind == api.ParticipantInfo.Kind.SIP), None)
        if caller is None:
            raise HTTPException(status_code=409, detail="The caller's phone line isn't in this call any more.")
        await lk.sip.transfer_sip_participant(api.TransferSIPParticipantRequest(
            room_name=call.call_room_id, participant_identity=caller.identity, transfer_to=destination, play_dialtone=False))
    except api.TwirpError as exc:
        if exc.code == "not_found":
            raise HTTPException(status_code=409, detail="This call has already ended.")
        raise HTTPException(status_code=502, detail=f"LiveKit refused the transfer: {exc.message}")
    finally:
        await lk.aclose()
    return destination


async def leave_voicemail(call: CallLog, config: dict, message: str | None) -> str:
    """Ask the voice agent in the room to say a message and hang up (e.g. when an answering machine picks up)."""
    text = (message or "").strip() or DEFAULT_VOICEMAIL
    if len(text) > MAX_VOICEMAIL_CHARS:
        raise HTTPException(status_code=422, detail=f"Keep the message under {MAX_VOICEMAIL_CHARS} characters.")
    lk = _require(config)
    try:
        await lk.room.send_data(api.SendDataRequest(
            room=call.call_room_id, topic=CONTROL_TOPIC, kind=api.DataPacket.Kind.RELIABLE,
            data=json.dumps({"action": "voicemail", "message": text}).encode()))
    except api.TwirpError as exc:
        if exc.code == "not_found":
            raise HTTPException(status_code=409, detail="This call has already ended.")
        raise HTTPException(status_code=502, detail=f"LiveKit didn't deliver the message: {exc.message}")
    finally:
        await lk.aclose()
    return text


def listen_token(call: CallLog, user_id: str, user_name: str, config: dict) -> dict:
    """A receive-only, hidden pass into the call's room for a supervisor to listen in."""
    settings = get_livekit_settings(config)
    if not (settings["url"] and settings["api_key"] and settings["api_secret"]):
        raise HTTPException(status_code=503, detail="LiveKit is not configured, so calls cannot be monitored.")
    grants = api.VideoGrants(room_join=True, room=call.call_room_id, can_subscribe=True, can_publish=False,
                             can_publish_data=False, hidden=True)
    token = (api.AccessToken(settings["api_key"], settings["api_secret"])
             .with_identity(f"monitor-{user_id}").with_name(f"{user_name} (listening)")
             .with_grants(grants).with_ttl(LISTEN_TTL).to_jwt())
    return {"url": settings["url"], "token": token, "room": call.call_room_id, "expires_in": int(LISTEN_TTL.total_seconds())}


async def transfer_request(db: Session, user, payload: dict, request) -> dict:
    from app.core.runtime_config import load_runtime_config
    from app.services import audit
    call = find_call(db, user.tenant_id, payload)
    destination = await transfer_call(call, load_runtime_config(), payload.get("to"))
    audit.record(db, action="call_transferred", entity="CallLog", entity_id=call.id, tenant_id=user.tenant_id,
                 user_id=user.id, details={"room": call.call_room_id, "to": destination}, request=request)
    return {"status": "ok", "room": call.call_room_id, "transferred_to": destination}


async def voicemail_request(db: Session, user, payload: dict, request) -> dict:
    from app.core.runtime_config import load_runtime_config
    from app.services import audit
    call = find_call(db, user.tenant_id, payload)
    text = await leave_voicemail(call, load_runtime_config(), payload.get("message"))
    audit.record(db, action="call_voicemail_left", entity="CallLog", entity_id=call.id, tenant_id=user.tenant_id,
                 user_id=user.id, details={"room": call.call_room_id, "characters": len(text)}, request=request)
    return {"status": "ok", "room": call.call_room_id, "message": text}

