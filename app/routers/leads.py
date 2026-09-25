import json
import csv
import io
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.lead import Lead, LeadActivity
from app.schemas.lead import (
    LeadCreate, LeadOut, LeadUpdate,
    LeadActivityCreate, LeadActivityOut
)
from app.core.auth_deps import get_current_user, RoleChecker
from app.models.user import User
from app.services import audit

router = APIRouter(prefix="/api/crm", tags=["Lead Management"])


def _assignee(db: Session, tenant_id: str, user_id: str | None) -> User | None:
    """The member a lead is assigned to; must be an active member of the same workspace."""
    if not user_id:
        return None
    member = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id, User.status == "active").first()
    if member is None:
        raise HTTPException(status_code=422, detail="Leads can only be assigned to an active member of this workspace.")
    return member


CLOSED_STATUSES = ("Converted", "Lost")
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
# Accepted header names (lower-case) for each lead field.
IMPORT_COLUMNS = {
    "name": ("name", "full name", "lead name", "contact name"),
    "phone": ("phone", "phone number", "mobile", "number", "contact number"),
    "email": ("email", "email address"),
    "company": ("company", "organisation", "organization", "business"),
    "status": ("status", "stage"),
    "notes": ("notes", "note", "comments"),
    "follow_up_date": ("follow up", "follow-up", "follow up date", "follow_up_date"),
}


def today_in(tz: str) -> str:
    try:
        return datetime.now(ZoneInfo(tz)).date().isoformat()
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {tz}")


def _custom_values(db: Session, tenant_id: str, current: dict | None, incoming: dict | None) -> dict:
    from app.services.lead_fields import FieldValueError, merge_values
    try:
        return merge_values(db, tenant_id, current, incoming)
    except FieldValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _notify_assigned(db: Session, lead: Lead, member: User, by: User) -> None:
    from app.services.notifications import notify
    notify(db, lead.tenant_id, [member.id], kind="lead_assigned", title=f"{by.name} assigned you {lead.name}",
           body=lead.phone, link="/crm")


def _ensure_phone_free(db: Session, tenant_id: str, phone: str, exclude_id: str | None = None) -> None:
    query = db.query(Lead).filter(Lead.tenant_id == tenant_id, Lead.phone == phone, Lead.deleted_at == None)
    if exclude_id:
        query = query.filter(Lead.id != exclude_id)
    existing = query.first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A lead with this phone number already exists ({existing.name}).")

@router.get("/leads", response_model=List[LeadOut])
def get_leads(
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    assigned_to: Optional[str] = Query(None, description="'me', 'unassigned', or a member id"),
    follow_up: Optional[str] = Query(None, pattern="^(overdue|today|upcoming)$", description="Open leads by follow-up date"),
    tz: str = Query("UTC", description="Timezone that decides what 'today' is"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve leads from CRM database with optional filters, keyword search, and tenant isolation."""
    query = db.query(Lead).filter(
        Lead.deleted_at == None,
        Lead.tenant_id == current_user.tenant_id
    )
    
    if status_filter:
        query = query.filter(Lead.status == status_filter)
        
    if assigned_to == "me":
        query = query.filter(Lead.assigned_user_id == current_user.id)
    elif assigned_to == "unassigned":
        query = query.filter(Lead.assigned_user_id.is_(None))
    elif assigned_to:
        query = query.filter(Lead.assigned_user_id == assigned_to)

    if follow_up:
        today = today_in(tz)
        query = query.filter(Lead.follow_up_date.isnot(None), Lead.status.notin_(CLOSED_STATUSES))
        if follow_up == "overdue":
            query = query.filter(Lead.follow_up_date < today)
        elif follow_up == "today":
            query = query.filter(Lead.follow_up_date == today)
        else:
            query = query.filter(Lead.follow_up_date > today)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(Lead.name.ilike(term) | Lead.phone.ilike(term) | Lead.company.ilike(term))

    return query.order_by(Lead.created_at.desc()).offset(offset).limit(limit).all()

@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new lead entry associated with the user's tenant."""
    _ensure_phone_free(db, current_user.tenant_id, payload.phone)
    member = _assignee(db, current_user.tenant_id, payload.assigned_user_id)
    custom = _custom_values(db, current_user.tenant_id, None, payload.custom_fields)
    lead = Lead(**payload.model_dump(exclude={"custom_fields"}), custom_fields=custom or None)
    if member:
        lead.assigned_agent = member.name
    lead.tenant_id = current_user.tenant_id
    db.add(lead)
    db.flush()
    
    # Log timeline activity for creation
    activity = LeadActivity(
        lead_id=lead.id,
        tenant_id=current_user.tenant_id,
        activity_type="crm_update",
        title="Lead Created",
        description=f"Lead record for {lead.name} was successfully created."
    )
    db.add(activity)
    
    db.commit()
    db.refresh(lead)
    if member and member.id != current_user.id:
        _notify_assigned(db, lead, member, current_user)

    # Trigger automation workflows asynchronously
    from app.services.workflow_engine import workflow_engine
    workflow_engine.dispatch_event("lead_created", lead, db)
    
    return lead

@router.post("/leads/import")
async def import_leads(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Manager"]))
):
    """Import leads from a CSV (header row required; name and phone columns). Rows with an invalid or
    already-known phone are skipped and reported. Imports don't fire workflows, so a big file can't
    start thousands of AI calls."""
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="CSV is larger than 2 MB. Split it into smaller files.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded.")
    reader = csv.DictReader(io.StringIO(text))
    headers = {h.strip().lower(): h for h in (reader.fieldnames or []) if h}
    column = {field: next((headers[a] for a in aliases if a in headers), None) for field, aliases in IMPORT_COLUMNS.items()}
    from app.services.lead_fields import FieldValueError, coerce, definitions
    custom_columns = [(f, headers.get(f.label.lower()) or headers.get(f.key)) for f in definitions(db, current_user.tenant_id)]
    custom_columns = [(f, col) for f, col in custom_columns if col]
    if not column["name"] or not column["phone"]:
        raise HTTPException(status_code=422, detail="The CSV needs a header row with 'name' and 'phone' columns.")

    known = {p for (p,) in db.query(Lead.phone).filter(Lead.tenant_id == current_user.tenant_id, Lead.deleted_at == None)}
    created, skipped = 0, []
    for row_number, row in enumerate(reader, start=2):
        if row_number - 1 > MAX_IMPORT_ROWS:
            skipped.append({"row": row_number, "reason": f"only the first {MAX_IMPORT_ROWS} rows are imported"})
            break
        values = {field: (row.get(col) or "").strip() for field, col in column.items() if col}
        if not any(values.values()):
            continue
        values["status"] = values.get("status") or "New"
        try:
            payload = LeadCreate(**values)
        except ValidationError as exc:
            first = exc.errors()[0]
            skipped.append({"row": row_number, "reason": f"{first['loc'][-1]}: {first['msg'].removeprefix('Value error, ')}"})
            continue
        custom = {}
        try:
            for field, col in custom_columns:
                value = coerce(field, row.get(col))
                if value is not None:
                    custom[field.key] = value
        except FieldValueError as exc:
            skipped.append({"row": row_number, "reason": str(exc)})
            continue
        if payload.phone in known:
            skipped.append({"row": row_number, "reason": f"{payload.phone} is already a lead"})
            continue
        known.add(payload.phone)
        db.add(Lead(**payload.model_dump(exclude={"custom_fields"}), custom_fields=custom or None, tenant_id=current_user.tenant_id))
        created += 1
    db.commit()
    audit.record(db, action="leads_imported", entity="Lead", tenant_id=current_user.tenant_id, user_id=current_user.id,
                 details={"created": created, "skipped": len(skipped), "file": file.filename}, request=request)
    return {"created": created, "skipped": skipped[:200], "skipped_count": len(skipped)}

@router.put("/leads/{id}", response_model=LeadOut)
def update_lead(
    id: str, 
    payload: LeadUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update lead property values and record updates in the timeline."""
    lead = db.query(Lead).filter(
        Lead.id == id, 
        Lead.deleted_at == None,
        Lead.tenant_id == current_user.tenant_id
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    original_status = lead.status
    newly_assigned = None
    update_data = payload.model_dump(exclude_unset=True)
    if update_data.get("phone") and update_data["phone"] != lead.phone:
        _ensure_phone_free(db, current_user.tenant_id, update_data["phone"], exclude_id=lead.id)
    if "custom_fields" in update_data:
        update_data["custom_fields"] = _custom_values(db, current_user.tenant_id, lead.custom_fields, update_data["custom_fields"]) or None
    if "assigned_user_id" in update_data and update_data["assigned_user_id"] != lead.assigned_user_id:
        member = _assignee(db, current_user.tenant_id, update_data["assigned_user_id"])
        update_data["assigned_agent"] = member.name if member else None
        if member and member.id != current_user.id:
            newly_assigned = member
        db.add(LeadActivity(
            lead_id=lead.id, tenant_id=current_user.tenant_id, activity_type="crm_update",
            title="Lead assigned" if member else "Lead unassigned",
            description=f"Assigned to {member.name} by {current_user.name}." if member else f"Unassigned by {current_user.name}.",
        ))
    for key, value in update_data.items():
        setattr(lead, key, value)
        
    lead.updated_at = datetime.now(timezone.utc)
    
    # Check if pipeline stage changed to log in timeline
    new_status = update_data.get("status")
    if new_status and new_status != original_status:
        activity = LeadActivity(
            lead_id=lead.id,
            tenant_id=current_user.tenant_id,
            activity_type="pipeline_change",
            title="Pipeline Stage Changed",
            description=f"Status changed from '{original_status}' to '{new_status}'."
        )
        db.add(activity)
        db.commit()
        
        # Trigger automation workflows asynchronously for pipeline status change
        from app.services.workflow_engine import workflow_engine
        workflow_engine.dispatch_event("lead_status_changed", lead, db)
    else:
        # Generic update log
        activity = LeadActivity(
            lead_id=lead.id,
            tenant_id=current_user.tenant_id,
            activity_type="crm_update",
            title="Lead Record Updated",
            description="Details of the lead record were modified."
        )
        db.add(activity)
        db.commit()
        
    db.commit()
    db.refresh(lead)
    if newly_assigned:
        _notify_assigned(db, lead, newly_assigned, current_user)
    return lead

@router.delete("/leads/{id}")
def delete_lead(
    id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin"]))
):
    """Soft-delete a lead by setting the deleted_at timestamp (Admins only)."""
    lead = db.query(Lead).filter(
        Lead.id == id, 
        Lead.deleted_at == None,
        Lead.tenant_id == current_user.tenant_id
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    lead.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok", "success": True}

@router.get("/leads/{lead_id}/timeline", response_model=List[LeadActivityOut])
def get_timeline(
    lead_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch timeline logs for the specified lead."""
    # Enforce tenant check
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == current_user.tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return db.query(LeadActivity).filter(
        LeadActivity.lead_id == lead_id,
        LeadActivity.tenant_id == current_user.tenant_id
    ).order_by(LeadActivity.created_at.desc()).all()

@router.post("/leads/{lead_id}/timeline", response_model=LeadActivityOut, status_code=status.HTTP_201_CREATED)
def add_timeline_activity(
    lead_id: str, 
    payload: LeadActivityCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Log an activity (notes, calls, manual summaries) manually on a lead timeline."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == current_user.tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    activity = LeadActivity(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        activity_type=payload.activity_type,
        title=payload.title,
        description=payload.description,
        metadata_json=payload.metadata_json
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity

@router.post("/leads/{lead_id}/score")
def score_lead(
    lead_id: str, 
    lead_data: dict, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Analyze lead attributes to classify priority (Hot/Warm/Cold)."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == current_user.tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    # AI calculation mockup. Evaluates NEET score, parent involvement, budget
    score = "Cold"
    explanation = "Minimal background data matching target qualifiers."
    neet = lead_data.get("neet_score") or lead.neet_score
    budget = lead_data.get("budget") or lead.budget
    parent = lead_data.get("parent_involved") or lead.parent_involved
    
    if neet and neet > 550:
        score = "Hot"
        explanation = "High NEET score (above 550) indicating strong academic intent."
    elif parent or (budget and "Lakh" in str(budget)):
        score = "Warm"
        explanation = "Financial indicators or parent involvement shows active interest."
        
    # Save the score
    lead.score = score
    lead.score_explanation = explanation
    db.commit()
    
    return {
        "status": "ok",
        "score": score,
        "explanation": explanation
    }
