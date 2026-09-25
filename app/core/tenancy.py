"""Binds a database session to a tenant so Postgres row-level security (migration 0005) applies."""
from __future__ import annotations

import logging

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.settings import settings

logger = logging.getLogger("tenancy")
_IS_POSTGRES = engine.dialect.name == "postgresql"
_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")


def bind_session_to_tenant(db: Session, tenant_id: str) -> None:
    """Every transaction this session runs from now on is limited to `tenant_id` (Postgres only)."""
    if not _IS_POSTGRES:
        return
    db.info["tenant_id"] = tenant_id
    # The transaction that loaded the user is already open; tag it too.
    db.execute(_SET_TENANT, {"tenant_id": tenant_id})


@event.listens_for(SessionLocal, "after_begin")
def _tag_new_transaction(session: Session, transaction, connection) -> None:
    tenant_id = session.info.get("tenant_id")
    if tenant_id and _IS_POSTGRES:
        connection.execute(_SET_TENANT, {"tenant_id": tenant_id})


def warn_if_rls_bypassed() -> None:
    """Superusers and BYPASSRLS roles ignore row-level security."""
    if not _IS_POSTGRES:
        return
    with engine.connect() as conn:
        bypass = conn.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar()
    if bypass:
        message = ("Database role bypasses row-level security (superuser or BYPASSRLS). "
                   "Connect with a regular role so tenant isolation is enforced by Postgres too.")
        if settings.is_local:
            logger.info(message)
        else:
            logger.warning(message)
