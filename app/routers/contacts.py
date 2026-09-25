from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.core.database import get_db
from app.models.call import CallLog
from app.models.appointment import Appointment
from db_backend import normalize_phone_number
from app.core.auth_deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/contacts", tags=["Contacts Aggregation"])

def _timestamp_rank(value: str | None) -> float:
    from datetime import datetime
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0

@router.get("")
def list_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Aggregate customer profiles grouping details by phone numbers."""
    logs = db.query(CallLog).filter(
        CallLog.tenant_id == current_user.tenant_id
    ).order_by(CallLog.created_at.desc()).limit(500).all()
    
    appointments = db.query(Appointment).filter(
        Appointment.tenant_id == current_user.tenant_id
    ).order_by(Appointment.scheduled_start).limit(500).all()
    
    contacts: Dict[str, Dict[str, Any]] = {}

    for row in logs:
        phone = row.phone_number or "unknown"
        item = contacts.setdefault(
            phone,
            {
                "phone_number": phone,
                "caller_name": row.caller_name or "",
                "total_calls": 0,
                "last_seen": row.created_at.isoformat() if row.created_at else "",
                "is_booked": False,
                "appointment_count": 0,
            },
        )
        item["total_calls"] += 1
        if not item["caller_name"] and row.caller_name:
            item["caller_name"] = row.caller_name
        if row.was_booked or "confirmed" in str(row.summary or "").lower():
            item["is_booked"] = True

    for apt in appointments:
        phone = normalize_phone_number(apt.contact_phone) or "unknown"
        item = contacts.setdefault(
            phone,
            {
                "phone_number": phone,
                "caller_name": apt.contact_name or "",
                "total_calls": 0,
                "last_seen": apt.scheduled_start,
                "is_booked": False,
                "appointment_count": 0,
            },
        )
        item["appointment_count"] += 1
        if not item["caller_name"] and apt.contact_name:
            item["caller_name"] = apt.contact_name
        if _timestamp_rank(apt.scheduled_start) > _timestamp_rank(item.get("last_seen")):
            item["last_seen"] = apt.scheduled_start
        if apt.status == "scheduled":
            item["is_booked"] = True

    sorted_contacts = sorted(
        contacts.values(),
        key=lambda x: _timestamp_rank(x.get("last_seen")),
        reverse=True
    )
    return sorted_contacts
