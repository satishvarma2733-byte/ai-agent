from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.database import get_db
from app.models.appointment import Appointment
from app.schemas.appointment import AppointmentOut, AppointmentCreate, AppointmentUpdate
from backend_events import (
    handle_booking_confirmed,
    handle_appointment_cancelled,
    handle_appointment_updated
)
from app.core.auth_deps import get_current_user
from app.services import calendar_sync, workflow_events
from app.services.appointment_store import find_overlap, to_utc_iso
from app.models.user import User

router = APIRouter(prefix="/api/appointments", tags=["Appointments Management"])

# A booking typed a minute or two late for "now" is still fine.
PAST_GRACE = timedelta(minutes=5)


def _refuse_if_calendar_busy(tenant_id: str, start_utc: str, end_utc: str, ignore: tuple[str, str] | None = None) -> None:
    if calendar_sync.busy_conflict(tenant_id, start_utc, end_utc, ignore=ignore):
        raise HTTPException(status_code=409, detail="Conflict: that time is busy in a connected calendar.")


def _parse(value: str, tz: ZoneInfo, field: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{field} must be a date and time, e.g. 2026-10-01T15:30")
    return moment.replace(tzinfo=tz) if moment.tzinfo is None else moment


def _validate_window(start: str, end: str, tz_name: str | None, *, allow_past: bool = False) -> None:
    try:
        tz = ZoneInfo(tz_name or "Asia/Kolkata")
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {tz_name}")
    starts, ends = _parse(start, tz, "scheduled_start"), _parse(end, tz, "scheduled_end")
    if ends <= starts:
        raise HTTPException(status_code=422, detail="The appointment must end after it starts.")
    if not allow_past and starts < datetime.now(timezone.utc) - PAST_GRACE:
        raise HTTPException(status_code=422, detail="The appointment cannot start in the past.")

@router.get("", response_model=List[AppointmentOut])
def get_appointments(
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List scheduled customer appointments with range limits."""
    query = db.query(Appointment).filter(Appointment.tenant_id == current_user.tenant_id)
    try:
        if start:
            query = query.filter(Appointment.scheduled_end > to_utc_iso(start, "UTC"))
        if end:
            query = query.filter(Appointment.scheduled_start < to_utc_iso(end, "UTC"))
    except ValueError:
        raise HTTPException(status_code=422, detail="start and end must be ISO date-times")
    return query.order_by(Appointment.scheduled_start).all()

@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Book a new customer appointment slot."""
    _validate_window(payload.scheduled_start, payload.scheduled_end, payload.timezone)
    start_utc = to_utc_iso(payload.scheduled_start, payload.timezone)
    end_utc = to_utc_iso(payload.scheduled_end, payload.timezone)
    if find_overlap(db, current_user.tenant_id, start_utc, end_utc):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: Time slot overlaps with an existing scheduled appointment."
        )
    _refuse_if_calendar_busy(current_user.tenant_id, start_utc, end_utc)

    appointment = Appointment(**payload.model_dump())
    appointment.scheduled_start, appointment.scheduled_end = start_utc, end_utc
    appointment.tenant_id = current_user.tenant_id
    appointment.source = "manual_ui"
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    calendar_sync.mark_changed(db, appointment)

    workflow_events.emit(db, appointment.tenant_id, "appointment_booked", phone=appointment.contact_phone, ref=appointment.id)

    # Confirm notifications trigger
    try:
        from app.core.runtime_config import load_runtime_config as _load_runtime_config
        config = _load_runtime_config()
        handle_booking_confirmed(
            appointment={
                "title": appointment.title,
                "contact_name": appointment.contact_name,
                "contact_phone": appointment.contact_phone,
                "scheduled_start": appointment.scheduled_start,
                "scheduled_end": appointment.scheduled_end,
                "timezone": appointment.timezone,
                "status": appointment.status,
                "notes": appointment.notes,
            },
            caller_name=appointment.contact_name,
            phone_number=appointment.contact_phone,
            ai_summary="Appointment booked successfully.",
            config=config
        )
    except Exception:
        pass
        
    return appointment

@router.patch("/{id}", response_model=AppointmentOut)
def update_appointment(
    id: str,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Edit scheduled appointment parameters."""
    apt = db.query(Appointment).filter(
        Appointment.id == id,
        Appointment.tenant_id == current_user.tenant_id
    ).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    update_data = payload.model_dump(exclude_unset=True)
    if {"scheduled_start", "scheduled_end", "timezone"} & update_data.keys():
        moved = update_data.get("scheduled_start", apt.scheduled_start) != apt.scheduled_start
        _validate_window(update_data.get("scheduled_start", apt.scheduled_start),
                         update_data.get("scheduled_end", apt.scheduled_end),
                         update_data.get("timezone", apt.timezone), allow_past=not moved)
        tz_name = update_data.get("timezone", apt.timezone)
        for key in ("scheduled_start", "scheduled_end"):
            if key in update_data:
                update_data[key] = to_utc_iso(update_data[key], tz_name)
    new_status = update_data.get("status", apt.status)
    if new_status == "scheduled" and find_overlap(db, apt.tenant_id, update_data.get("scheduled_start", apt.scheduled_start),
                                                  update_data.get("scheduled_end", apt.scheduled_end), exclude_id=apt.id):
        raise HTTPException(status_code=409, detail="Conflict: Time slot overlaps with an existing scheduled appointment.")
    new_start = update_data.get("scheduled_start", apt.scheduled_start)
    new_end = update_data.get("scheduled_end", apt.scheduled_end)
    if new_status == "scheduled" and (apt.status != "scheduled" or (new_start, new_end) != (apt.scheduled_start, apt.scheduled_end)):
        # Its own calendar event still sits at the current slot.
        own = (apt.scheduled_start, apt.scheduled_end) if apt.status == "scheduled" else None
        _refuse_if_calendar_busy(apt.tenant_id, new_start, new_end, ignore=own)
    for key, value in update_data.items():
        setattr(apt, key, value)
        
    apt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(apt)
    calendar_sync.mark_changed(db, apt)
    
    try:
        from app.core.runtime_config import load_runtime_config as _load_runtime_config
        config = _load_runtime_config()
        handle_appointment_updated({
            "title": apt.title,
            "contact_name": apt.contact_name,
            "contact_phone": apt.contact_phone,
            "scheduled_start": apt.scheduled_start,
            "scheduled_end": apt.scheduled_end,
            "status": apt.status,
        }, config=config)
    except Exception:
        pass
        
    return apt

@router.post("/{id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel a booked appointment with an optional reason text."""
    apt = db.query(Appointment).filter(
        Appointment.id == id,
        Appointment.tenant_id == current_user.tenant_id
    ).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    reason = payload.get("reason", "")
    apt.status = "cancelled"
    
    notes = (apt.notes or "").strip()
    if reason:
        notes = f"{notes}\n\nCancellation reason: {reason}".strip()
    apt.notes = notes
    apt.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(apt)
    calendar_sync.mark_changed(db, apt)
    
    try:
        from app.core.runtime_config import load_runtime_config as _load_runtime_config
        config = _load_runtime_config()
        handle_appointment_cancelled({
            "title": apt.title,
            "contact_name": apt.contact_name,
            "contact_phone": apt.contact_phone,
            "scheduled_start": apt.scheduled_start,
            "scheduled_end": apt.scheduled_end,
            "status": apt.status,
            "notes": apt.notes,
        }, reason=reason, config=config)
    except Exception:
        pass
        
    return apt
