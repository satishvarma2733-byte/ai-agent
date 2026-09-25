"""Audit trail for security-relevant and administrative actions."""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def record(
    db: Session,
    *,
    action: str,
    entity: str,
    tenant_id: str | None,
    user_id: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
    commit: bool = True,
) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=json.dumps(details, default=str) if details else None,
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent", "")[:300] if request else None),
    ))
    if commit:
        db.commit()
