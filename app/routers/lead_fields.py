"""Workspace-defined lead fields."""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.models.lead import Lead, LeadField
from app.models.user import User
from app.services import audit
from app.services.lead_fields import MAX_FIELDS, definitions, slugify

router = APIRouter(prefix="/api/crm/fields", tags=["Lead Fields"])
require_admin = RoleChecker(["Admin"])

FieldType = Literal["text", "number", "date", "select", "boolean"]


def _clean_options(options: Optional[list[str]]) -> Optional[list[str]]:
    if options is None:
        return None
    cleaned = []
    for option in options:
        text = str(option).strip()
        if text and text.lower() not in (o.lower() for o in cleaned):
            cleaned.append(text[:100])
    return cleaned


class LeadFieldIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    field_type: FieldType
    options: Optional[List[str]] = Field(default=None, max_length=100)
    key: Optional[str] = Field(default=None, max_length=60)

    @field_validator("options")
    @classmethod
    def _options(cls, value):
        return _clean_options(value)


class LeadFieldUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    options: Optional[List[str]] = Field(default=None, max_length=100)
    position: Optional[int] = Field(default=None, ge=0, le=1000)

    @field_validator("options")
    @classmethod
    def _options(cls, value):
        return _clean_options(value)


class LeadFieldOut(BaseModel):
    id: str
    key: str
    label: str
    field_type: str
    options: Optional[List[str]] = None
    position: int

    class Config:
        from_attributes = True


def _get(db: Session, field_id: str, tenant_id: str) -> LeadField:
    field = db.query(LeadField).filter(LeadField.id == field_id, LeadField.tenant_id == tenant_id).first()
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


@router.get("", response_model=List[LeadFieldOut])
def list_fields(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return definitions(db, current_user.tenant_id)


@router.post("", response_model=LeadFieldOut, status_code=status.HTTP_201_CREATED)
def create_field(payload: LeadFieldIn, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    existing = definitions(db, current_user.tenant_id)
    if len(existing) >= MAX_FIELDS:
        raise HTTPException(status_code=422, detail=f"A workspace can have up to {MAX_FIELDS} lead fields.")
    if payload.field_type == "select" and not payload.options:
        raise HTTPException(status_code=422, detail="A choice field needs at least one option.")
    key = slugify(payload.key or payload.label)
    if any(f.key == key for f in existing):
        raise HTTPException(status_code=409, detail=f"A field with the key '{key}' already exists.")
    field = LeadField(tenant_id=current_user.tenant_id, key=key, label=payload.label.strip(), field_type=payload.field_type,
                      options=payload.options if payload.field_type == "select" else None,
                      position=max((f.position for f in existing), default=-1) + 1)
    db.add(field)
    db.commit()
    db.refresh(field)
    audit.record(db, action="lead_field_created", entity="LeadField", entity_id=field.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"key": key, "type": field.field_type}, request=request)
    return field


@router.patch("/{field_id}", response_model=LeadFieldOut)
def update_field(field_id: str, payload: LeadFieldUpdate, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    """Rename, reorder or change a choice list. The key and type are fixed, since stored values depend on them."""
    field = _get(db, field_id, current_user.tenant_id)
    if payload.label is not None:
        field.label = payload.label.strip()
    if payload.position is not None:
        field.position = payload.position
    if payload.options is not None:
        if field.field_type != "select":
            raise HTTPException(status_code=422, detail="Only choice fields have options.")
        if not payload.options:
            raise HTTPException(status_code=422, detail="A choice field needs at least one option.")
        field.options = payload.options
    db.commit()
    db.refresh(field)
    return field


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field(field_id: str, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    """Delete a field and its value on every lead."""
    field = _get(db, field_id, current_user.tenant_id)
    for lead in db.query(Lead).filter(Lead.tenant_id == current_user.tenant_id, Lead.custom_fields.isnot(None)):
        if field.key in (lead.custom_fields or {}):
            lead.custom_fields = {k: v for k, v in lead.custom_fields.items() if k != field.key}
    key = field.key
    db.delete(field)
    db.commit()
    audit.record(db, action="lead_field_deleted", entity="LeadField", entity_id=field_id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"key": key}, request=request)
