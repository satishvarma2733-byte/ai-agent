"""Connecting Google Calendar and Zoho Calendar to a workspace."""
import logging
from datetime import timezone
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import config_crypto
from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.core.settings import settings
from app.core.tenancy import bind_session_to_tenant
from app.models.calendar import AppointmentCalendarEvent, CalendarConnection
from app.models.user import User
from app.schemas.common import UTCDateTime
from app.services import audit, calendar_sync
from app.services import calendar_providers as cp

logger = logging.getLogger("calendar-router")

router = APIRouter(prefix="/api/integrations/calendar", tags=["Calendar sync"])


class CalendarStatusOut(BaseModel):
    provider: str
    label: str
    available: bool  # the server has OAuth credentials for this provider
    connected: bool
    account_email: Optional[str] = None
    status: Optional[str] = None
    last_error: Optional[str] = None
    last_synced_at: Optional[UTCDateTime] = None
    pending: int = 0
    failed: int = 0


class ConnectOut(BaseModel):
    url: str


class SyncOut(BaseModel):
    pushed: int
    changed: int
    last_synced_at: Optional[UTCDateTime] = None


def _provider(name: str) -> cp.Provider:
    impl = calendar_sync.provider(name)
    if impl is None:
        raise HTTPException(status_code=404, detail="Unknown calendar provider")
    return impl


def _connection(db: Session, tenant_id: str, name: str) -> CalendarConnection | None:
    return db.query(CalendarConnection).filter(CalendarConnection.tenant_id == tenant_id,
                                               CalendarConnection.provider == name).first()


def _request_base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("", response_model=List[CalendarStatusOut])
def calendar_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Which calendars this workspace has connected, and how their sync is going."""
    out = []
    for name, impl in cp.PROVIDERS.items():
        conn = _connection(db, current_user.tenant_id, name)
        row = CalendarStatusOut(provider=name, label=impl.label, available=impl.configured(), connected=conn is not None)
        if conn:
            per_state = dict(db.query(AppointmentCalendarEvent.state, func.count()).filter(
                AppointmentCalendarEvent.connection_id == conn.id).group_by(AppointmentCalendarEvent.state).all())
            row.account_email, row.status, row.last_error = conn.account_email, conn.status, conn.last_error
            row.last_synced_at = conn.last_synced_at.replace(tzinfo=timezone.utc) if conn.last_synced_at else None
            row.pending, row.failed = per_state.get("pending", 0), per_state.get("error", 0)
        out.append(row)
    return out


@router.post("/{provider}/connect", response_model=ConnectOut)
def start_connect(provider: str, request: Request, current_user: User = Depends(RoleChecker(["Admin"]))):
    """The provider's sign-in page. After consent it returns to /callback, which stores the connection."""
    impl = _provider(provider)
    if not impl.configured():
        raise HTTPException(status_code=503, detail=f"{impl.label} isn't set up on this server yet "
                                                    f"({impl.client_id_env} and {impl.client_secret_env}).")
    try:
        calendar_sync.ensure_can_store_tokens()
    except config_crypto.SecretsKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    state = calendar_sync.make_state(current_user.tenant_id, current_user.id, provider)
    return ConnectOut(url=impl.auth_url(state, calendar_sync.redirect_uri(provider, _request_base(request))))


@router.get("/{provider}/callback", include_in_schema=False)
def finish_connect(provider: str, request: Request, code: str = "", state: str = "", error: str = "",
                   db: Session = Depends(get_db)):
    """Where the provider sends the admin back. Not called by the dashboard directly."""
    impl = _provider(provider)

    def back(result: str, message: str = "") -> RedirectResponse:
        query = urlencode({"calendar": provider, "result": result, **({"message": message} if message else {})})
        return RedirectResponse(f"{settings.frontend_base_url}/appointments?{query}", status_code=302)

    data = calendar_sync.read_state(state, provider)
    if data is None:
        return back("error", "The sign-in link expired. Try connecting again.")
    if error or not code:
        return back("error", "Access wasn't granted." if error == "access_denied" else f"{impl.label} returned: {error or 'no code'}")
    bind_session_to_tenant(db, data["t"])
    user = db.get(User, data["u"])
    from app.services import memberships
    if user is None or not memberships.is_active_member(db, user.id, data["t"]):
        return back("error", "Your account can no longer connect calendars.")
    try:
        account = impl.connect(code, calendar_sync.redirect_uri(provider, _request_base(request)), dict(request.query_params))
        conn = calendar_sync.save_connection(db, data["t"], data["u"], provider, account)
    except cp.CalendarApiError as exc:
        logger.warning("[CAL] %s connect failed for %s: %s", provider, data["t"], exc)
        return back("error", str(exc)[:200])
    audit.record(db, action="calendar_connected", entity="CalendarConnection", entity_id=conn.id, tenant_id=data["t"],
                 user_id=data["u"], details={"provider": provider, "account": account.email}, request=request)
    return back("connected")


@router.post("/{provider}/sync", response_model=SyncOut)
def sync_calendar(provider: str, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Manager"]))):
    """Retry failed events and read changes now instead of waiting for the next automatic run."""
    _provider(provider)
    conn = _connection(db, current_user.tenant_id, provider)
    if conn is None:
        raise HTTPException(status_code=404, detail="This calendar isn't connected.")
    if conn.status == "error" and conn.last_error and "Connect the calendar again" in conn.last_error:
        raise HTTPException(status_code=409, detail=conn.last_error)
    result = calendar_sync.sync_now(current_user.tenant_id)
    db.refresh(conn)
    return SyncOut(**result, last_synced_at=conn.last_synced_at.replace(tzinfo=timezone.utc) if conn.last_synced_at else None)


@router.delete("/{provider}", status_code=204)
def disconnect_calendar(provider: str, request: Request, db: Session = Depends(get_db),
                        current_user: User = Depends(RoleChecker(["Admin"]))):
    """Stop syncing and revoke aVn's access. Events already in the calendar stay."""
    _provider(provider)
    conn = _connection(db, current_user.tenant_id, provider)
    if conn is None:
        raise HTTPException(status_code=404, detail="This calendar isn't connected.")
    conn_id = conn.id
    calendar_sync.disconnect(db, conn)
    audit.record(db, action="calendar_disconnected", entity="CalendarConnection", entity_id=conn_id,
                 tenant_id=current_user.tenant_id, user_id=current_user.id, details={"provider": provider}, request=request)


# ── iCalendar feed (Apple Calendar, Outlook, any calendar app that subscribes to a URL) ─────────

# Its own paths: under /api/integrations/calendar, "/ical" would be taken for a provider name.
ical_router = APIRouter(tags=["Calendar sync"])


class IcalFeedOut(BaseModel):
    enabled: bool
    url: Optional[str] = None
    webcal_url: Optional[str] = None
    last_fetched_at: Optional[UTCDateTime] = None


def _feed_out(feed, request: Request) -> IcalFeedOut:
    if feed is None:
        return IcalFeedOut(enabled=False)
    token = config_crypto.decrypt(feed.token)
    base = (settings.public_api_url or _request_base(request)).rstrip("/")
    url = f"{base}/api/ical/{token}.ics"
    return IcalFeedOut(enabled=True, url=url, webcal_url="webcal://" + url.split("://", 1)[1],
                       last_fetched_at=feed.last_fetched_at.replace(tzinfo=timezone.utc) if feed.last_fetched_at else None)


@ical_router.get("/api/integrations/ical-feed", response_model=IcalFeedOut)
def ical_feed_status(request: Request, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin"]))):
    from app.models.sms import CalendarFeed
    return _feed_out(db.query(CalendarFeed).filter(CalendarFeed.tenant_id == current_user.tenant_id).first(), request)


@ical_router.post("/api/integrations/ical-feed/rotate", response_model=IcalFeedOut)
def rotate_ical_feed(request: Request, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin"]))):
    """Turn the feed on, or replace its URL: anyone subscribed to the old URL stops receiving updates."""
    from datetime import datetime

    from app.core.security import hash_token, new_opaque_token
    from app.models.sms import CalendarFeed
    token = new_opaque_token()
    feed = db.query(CalendarFeed).filter(CalendarFeed.tenant_id == current_user.tenant_id).first()
    if feed is None:
        feed = CalendarFeed(tenant_id=current_user.tenant_id, created_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.add(feed)
    feed.token_hash = hash_token(token)
    feed.token = config_crypto.encrypt(token) if config_crypto.encryption_available() else token
    feed.last_fetched_at = None
    db.commit()
    audit.record(db, action="ical_feed_rotated", entity="CalendarFeed", entity_id=feed.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return _feed_out(feed, request)


@ical_router.delete("/api/integrations/ical-feed", status_code=204)
def delete_ical_feed(request: Request, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin"]))):
    from app.models.sms import CalendarFeed
    db.query(CalendarFeed).filter(CalendarFeed.tenant_id == current_user.tenant_id).delete()
    db.commit()
    audit.record(db, action="ical_feed_deleted", entity="CalendarFeed", tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)


ICAL_FETCHES_PER_MINUTE = 30


@ical_router.get("/api/ical/{token}.ics", include_in_schema=False)
def ical_feed(token: str, db: Session = Depends(get_db)):
    """Public, by secret URL: the workspace's appointments from 30 days ago to a year ahead."""
    from datetime import datetime

    from fastapi.responses import Response

    from app.core import ratelimit
    from app.core.security import hash_token
    from app.models.sms import CalendarFeed
    from app.models.tenant import Tenant
    from app.services import ical_feed as ical
    feed = db.query(CalendarFeed).filter(CalendarFeed.token_hash == hash_token(token)).first()
    if feed is None:
        raise HTTPException(status_code=404, detail="Not Found")
    key = f"ical:{feed.id}"
    if ratelimit.is_limited(key, ICAL_FETCHES_PER_MINUTE, 60):
        raise HTTPException(status_code=429, detail="Too many requests")
    ratelimit.hit(key, 60)
    bind_session_to_tenant(db, feed.tenant_id)
    tenant = db.get(Tenant, feed.tenant_id)
    body = ical.render(db, feed.tenant_id, tenant.name if tenant else "aVn")
    feed.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return Response(content=body, media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "private, max-age=300", "Content-Disposition": 'inline; filename="appointments.ics"'})
