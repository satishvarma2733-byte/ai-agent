"""Workspace-defined lead fields: definitions and value validation."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.lead import LeadField

FIELD_TYPES = ("text", "number", "date", "select", "boolean")
MAX_FIELDS = 50
MAX_TEXT = 1000
_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


class FieldValueError(ValueError):
    pass


def slugify(label: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return key[:60] or "field"


def definitions(db: Session, tenant_id: str) -> list[LeadField]:
    return db.query(LeadField).filter(LeadField.tenant_id == tenant_id).order_by(LeadField.position, LeadField.created_at).all()


def coerce(field: LeadField, value: Any) -> Any:
    """The stored form of `value` for this field, or None to clear it."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    kind = field.field_type
    if kind == "text":
        text = str(value).strip()
        if len(text) > MAX_TEXT:
            raise FieldValueError(f"{field.label} is longer than {MAX_TEXT} characters")
        return text
    if kind == "number":
        if isinstance(value, bool):
            raise FieldValueError(f"{field.label} must be a number")
        try:
            number = float(str(value).replace(",", "").strip())
        except ValueError:
            raise FieldValueError(f"{field.label} must be a number")
        return int(number) if number.is_integer() else number
    if kind == "date":
        text = str(value).strip()
        try:
            return (date.fromisoformat(text) if len(text) == 10 else datetime.fromisoformat(text.replace("Z", "+00:00")).date()).isoformat()
        except ValueError:
            raise FieldValueError(f"{field.label} must be a date like 2026-10-01")
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise FieldValueError(f"{field.label} must be yes or no")
    if kind == "select":
        text = str(value).strip()
        for option in field.options or []:
            if option.lower() == text.lower():
                return option
        raise FieldValueError(f"{field.label} must be one of: {', '.join(field.options or [])}")
    raise FieldValueError(f"{field.label} has an unknown type")


def merge_values(db: Session, tenant_id: str, current: dict | None, incoming: dict | None) -> dict:
    """Apply `incoming` (key -> value; empty clears) onto `current`, validating every key and value."""
    result = dict(current or {})
    if not incoming:
        return result
    fields = {f.key: f for f in definitions(db, tenant_id)}
    for key, value in incoming.items():
        field = fields.get(key)
        if field is None:
            raise FieldValueError(f"Unknown field '{key}'")
        cleaned = coerce(field, value)
        if cleaned is None:
            result.pop(key, None)
        else:
            result[key] = cleaned
    return result
