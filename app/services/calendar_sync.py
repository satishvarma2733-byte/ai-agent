"""Keeps each workspace's connected calendars (Google, Zoho) in step with its appointments.

- Push: every appointment change marks its calendar events pending; a worker writes them with retries.
- Pull: events aVn created that the owner moved or deleted in their calendar update the appointment.
- Busy times: bookings and the voice agent's free slots avoid times that are busy in a connected calendar.
  If a calendar can't be reached, booking carries on (the outage is logged and shown on the connection).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

import config_crypto
from app.core.database import SessionLocal
from app.core.security import SECRET_KEY
from app.core.settings import settings
from app.models.appointment import Appointment
from app.models.calendar import AppointmentCalendarEvent, CalendarConnection
from app.services import calendar_providers as cp

logger = logging.getLogger("calendar-sync")

PUSH_SECONDS = 15
PULL_SECONDS = 300
MAX_ATTEMPTS = 5
STATE_TTL = 600
BUSY_CACHE_SECONDS = 60
PULL_BATCH = 100

_busy_cache: dict[tuple, tuple[float, list[tuple[str, str]]]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def provider(name: str) -> cp.Provider | None:
    return cp.PROVIDERS.get(name)


# --- OAuth ---------------------------------------------------------------------------------------

def make_state(tenant_id: str, user_id: str, provider_name: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps(
        {"t": tenant_id, "u": user_id, "p": provider_name, "exp": int(time.time()) + STATE_TTL,
         "n": os.urandom(8).hex()}).encode()).decode().rstrip("=")
    return f"{body}.{_state_sig(body)}"


def read_state(state: str, provider_name: str) -> dict | None:
    body, _, sig = (state or "").partition(".")
    if not body or not hmac.compare_digest(_state_sig(body), sig):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if data.get("p") != provider_name or data.get("exp", 0) < time.time():
        return None
    return data


def _state_sig(body: str) -> str:
    return hmac.new(f"calendar-oauth:{SECRET_KEY}".encode(), body.encode(), hashlib.sha256).hexdigest()


def redirect_uri(provider_name: str, request_base: str) -> str:
    base = (settings.public_api_url or request_base).rstrip("/")
    return f"{base}/api/integrations/calendar/{provider_name}/callback"


def ensure_can_store_tokens() -> None:
    """Calendar tokens are credentials: outside local development they must be encrypted at rest."""
    if not config_crypto.encryption_available() and not settings.is_local:
        raise config_crypto.SecretsKeyError("Set SECRETS_ENCRYPTION_KEY before connecting a calendar.")


def _seal(value: str | None) -> str | None:
    if not value:
        return value
    return config_crypto.encrypt(value) if config_crypto.encryption_available() else value


def _open(value: str | None) -> str | None:
    return config_crypto.decrypt(value) if value else value


def save_connection(db: Session, tenant_id: str, user_id: str | None, provider_name: str,
                    account: cp.Account) -> CalendarConnection:
    conn = db.query(CalendarConnection).filter(CalendarConnection.tenant_id == tenant_id,
                                               CalendarConnection.provider == provider_name).first()
    if conn is None:
        conn = CalendarConnection(tenant_id=tenant_id, provider=provider_name, created_at=_now())
        db.add(conn)
    elif conn.calendar_id != account.calendar_id or conn.account_email != account.email:
        # A different calendar: events written to the old one no longer apply.
        db.query(AppointmentCalendarEvent).filter(AppointmentCalendarEvent.connection_id == conn.id).delete()
    conn.account_email, conn.calendar_id, conn.accounts_url = account.email, account.calendar_id, account.accounts_url
    conn.refresh_token = _seal(account.tokens.refresh_token)
    conn.access_token = _seal(account.tokens.access_token)
    conn.access_expires_at = _now() + timedelta(seconds=account.tokens.expires_in)
    conn.status, conn.last_error, conn.connected_by = "active", None, user_id
    db.commit()
    # Upcoming bookings go into the newly connected calendar too.
    upcoming = db.query(Appointment).filter(
        Appointment.tenant_id == tenant_id, Appointment.status == "scheduled",
        Appointment.scheduled_end > datetime.now(timezone.utc).isoformat(),
    ).all()
    for apt in upcoming:
        _mark(db, conn, apt)
    db.commit()
    _busy_cache.clear()
    return conn


def disconnect(db: Session, conn: CalendarConnection) -> None:
    """Stop syncing. Events already in the calendar stay there; the grant is revoked when possible."""
    impl = provider(conn.provider)
    try:
        token = _open(conn.refresh_token)
        with cp.http() as client:
            if conn.provider == "google":
                client.post("https://oauth2.googleapis.com/revoke", data={"token": token})
            elif conn.provider == "zoho":
                client.post(f"{conn.accounts_url or impl.default_accounts_url}/oauth/v2/token/revoke", params={"token": token})
    except Exception as exc:  # revocation is best effort; the stored tokens are deleted either way
        logger.warning("[CAL] Revoking %s access failed: %s", conn.provider, exc)
    # Explicit: SQLite (local development) doesn't enforce the cascade.
    db.query(AppointmentCalendarEvent).filter(AppointmentCalendarEvent.connection_id == conn.id).delete()
    db.delete(conn)
    db.commit()
    _busy_cache.clear()


def _access_token(db: Session, conn: CalendarConnection, force: bool = False) -> str:
    if not force and conn.access_token and conn.access_expires_at and conn.access_expires_at > _now() + timedelta(seconds=60):
        return _open(conn.access_token)
    impl = provider(conn.provider)
    try:
        tokens = impl.refresh(_open(conn.refresh_token), conn.accounts_url)
    except cp.ReconnectRequired as exc:
        conn.status, conn.last_error = "error", str(exc)
        db.commit()
        raise
    conn.access_token = _seal(tokens.access_token)
    conn.access_expires_at = _now() + timedelta(seconds=tokens.expires_in)
    if tokens.refresh_token:
        conn.refresh_token = _seal(tokens.refresh_token)
    db.commit()
    return tokens.access_token


def _call(db: Session, conn: CalendarConnection, fn):
    """Run fn(token), refreshing the access token once if the provider says it has expired."""
    try:
        return fn(_access_token(db, conn))
    except cp.CalendarApiError as exc:
        if not exc.unauthorized or isinstance(exc, cp.ReconnectRequired):
            raise
        return fn(_access_token(db, conn, force=True))


# --- Marking appointments for push ---------------------------------------------------------------

def _mark(db: Session, conn: CalendarConnection, apt: Appointment) -> None:
    link = db.query(AppointmentCalendarEvent).filter(AppointmentCalendarEvent.appointment_id == apt.id,
                                                     AppointmentCalendarEvent.connection_id == conn.id).first()
    if link is None:
        if apt.status != "scheduled":
            return  # never written to this calendar, nothing to remove
        link = AppointmentCalendarEvent(tenant_id=apt.tenant_id, appointment_id=apt.id, connection_id=conn.id)
        db.add(link)
    link.state, link.attempts, link.next_attempt_at, link.last_error = "pending", 0, _now(), None
    link.updated_at = _now()


def mark_changed(db: Session, apt: Appointment) -> None:
    """Call after an appointment is created, moved, edited or cancelled. Commits on its own. Never raises."""
    try:
        conns = db.query(CalendarConnection).filter(CalendarConnection.tenant_id == apt.tenant_id).all()
        for conn in conns:
            _mark(db, conn, apt)
        if conns:
            db.commit()
            _busy_cache.clear()
    except Exception as exc:
        db.rollback()
        logger.error("[CAL] Could not queue calendar update for %s: %s", apt.id, exc)


def mark_changed_by_id(tenant_id: str, appointment_id: str) -> None:
    db = SessionLocal()
    try:
        apt = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.tenant_id == tenant_id).first()
        if apt is not None:
            mark_changed(db, apt)
    finally:
        db.close()


# --- Push ----------------------------------------------------------------------------------------

def _data(apt: Appointment) -> cp.AppointmentData:
    return cp.AppointmentData(id=apt.id, tenant_id=apt.tenant_id, title=apt.title, contact_name=apt.contact_name,
                              contact_phone=apt.contact_phone, start=apt.scheduled_start, end=apt.scheduled_end,
                              timezone=apt.timezone or "Asia/Kolkata", notes=apt.notes or "")


def push_one(db: Session, link: AppointmentCalendarEvent) -> bool:
    conn = db.get(CalendarConnection, link.connection_id)
    apt = db.get(Appointment, link.appointment_id)
    if conn is None or apt is None:
        return False
    impl = provider(conn.provider)
    ref = cp.EventRef(link.external_id, link.etag) if link.external_id else None
    try:
        if apt.status == "cancelled":
            if ref:
                _call(db, conn, lambda t: impl.delete_event(t, conn.calendar_id, ref, conn.accounts_url))
            link.external_id = link.etag = None
        elif apt.status == "scheduled":
            data = _data(apt)
            if ref:
                new = _call(db, conn, lambda t: impl.update_event(t, conn.calendar_id, ref, data, conn.accounts_url))
            else:
                new = _call(db, conn, lambda t: impl.create_event(t, conn.calendar_id, data, conn.accounts_url))
            link.external_id, link.etag = new.external_id, new.etag
            link.synced_start, link.synced_end = apt.scheduled_start, apt.scheduled_end
        # A completed appointment keeps its event as it is.
        link.state, link.attempts, link.last_error, link.next_attempt_at = "synced", 0, None, None
        link.updated_at = _now()
        conn.last_synced_at = _now()
        if conn.status == "error" and conn.last_error and "Connect the calendar again" not in conn.last_error:
            conn.status, conn.last_error = "active", None
        db.commit()
        return True
    except cp.ReconnectRequired:
        db.rollback()
        return False  # stays pending until an admin reconnects
    except Exception as exc:
        db.rollback()
        link = db.get(AppointmentCalendarEvent, link.id)
        link.attempts += 1
        link.last_error = str(exc)[:500]
        link.state = "error" if link.attempts >= MAX_ATTEMPTS else "pending"
        link.next_attempt_at = _now() + timedelta(seconds=30 * 2 ** link.attempts)
        link.updated_at = _now()
        db.commit()
        logger.warning("[CAL] %s push for appointment %s failed (attempt %s): %s",
                       conn.provider, link.appointment_id, link.attempts, exc)
        return False


def push_pending(tenant_id: str | None = None, limit: int = 50) -> int:
    db = SessionLocal()
    try:
        query = db.query(AppointmentCalendarEvent).join(
            CalendarConnection, CalendarConnection.id == AppointmentCalendarEvent.connection_id,
        ).filter(
            AppointmentCalendarEvent.state == "pending", CalendarConnection.status == "active",
            (AppointmentCalendarEvent.next_attempt_at.is_(None)) | (AppointmentCalendarEvent.next_attempt_at <= _now()),
        )
        if tenant_id:
            query = query.filter(AppointmentCalendarEvent.tenant_id == tenant_id)
        links = query.order_by(AppointmentCalendarEvent.updated_at).limit(limit).all()
        return sum(push_one(db, link) for link in links)
    finally:
        db.close()


# --- Pull ----------------------------------------------------------------------------------------

def pull_changes(tenant_id: str | None = None) -> int:
    """Apply moves and deletions made in the calendar to aVn events. Returns how many appointments changed."""
    from app.services import notifications
    db = SessionLocal()
    changed = 0
    try:
        query = db.query(CalendarConnection).filter(CalendarConnection.status == "active")
        if tenant_id:
            query = query.filter(CalendarConnection.tenant_id == tenant_id)
        for conn in query.all():
            impl = provider(conn.provider)
            links = db.query(AppointmentCalendarEvent).join(
                Appointment, Appointment.id == AppointmentCalendarEvent.appointment_id,
            ).filter(
                AppointmentCalendarEvent.connection_id == conn.id, AppointmentCalendarEvent.state == "synced",
                AppointmentCalendarEvent.external_id.isnot(None), Appointment.status == "scheduled",
                Appointment.scheduled_end > datetime.now(timezone.utc).isoformat(),
            ).order_by(Appointment.scheduled_start).limit(PULL_BATCH).all()
            try:
                for link in links:
                    ref = cp.EventRef(link.external_id, link.etag)
                    remote = _call(db, conn, lambda t: impl.get_event(t, conn.calendar_id, ref, conn.accounts_url))
                    apt = db.get(Appointment, link.appointment_id)
                    message = None
                    if remote.cancelled:
                        apt.status = "cancelled"
                        apt.notes = f"{(apt.notes or '').strip()}\n\nCancelled in {impl.label}.".strip()
                        link.external_id = link.etag = None
                        message = f"{apt.contact_name}'s appointment was cancelled in {impl.label}"
                    elif remote.start and remote.end and (remote.start, remote.end) != (link.synced_start, link.synced_end):
                        apt.scheduled_start, apt.scheduled_end = remote.start, remote.end
                        link.synced_start, link.synced_end, link.etag = remote.start, remote.end, remote.etag
                        local = datetime.fromisoformat(remote.start).astimezone(ZoneInfo(apt.timezone or "Asia/Kolkata"))
                        message = f"{apt.contact_name}'s appointment was moved in {impl.label} to {local.strftime('%a %d %b, %I:%M %p')}"
                    elif remote.etag:
                        link.etag = remote.etag
                    if message:
                        apt.updated_at = datetime.now(timezone.utc)
                        # Other connected calendars follow the change.
                        for other in db.query(CalendarConnection).filter(CalendarConnection.tenant_id == conn.tenant_id,
                                                                         CalendarConnection.id != conn.id).all():
                            _mark(db, other, apt)
                        db.commit()
                        notifications.notify(db, conn.tenant_id, notifications.managers(db, conn.tenant_id),
                                             kind="appointment_changed", title=message, link="/appointments")
                        changed += 1
                    else:
                        db.commit()
                conn.last_synced_at = _now()
                db.commit()
            except cp.ReconnectRequired:
                db.rollback()
            except Exception as exc:
                db.rollback()
                logger.warning("[CAL] Reading %s changes for %s failed: %s", conn.provider, conn.tenant_id, exc)
                conn = db.get(CalendarConnection, conn.id)
                conn.last_error = str(exc)[:500]
                db.commit()
        if changed:
            _busy_cache.clear()
        return changed
    finally:
        db.close()


def sync_now(tenant_id: str) -> dict:
    """Retry failed events, push everything pending and read calendar changes for one workspace."""
    db = SessionLocal()
    try:
        db.query(AppointmentCalendarEvent).filter(
            AppointmentCalendarEvent.tenant_id == tenant_id, AppointmentCalendarEvent.state == "error",
        ).update({"state": "pending", "attempts": 0, "next_attempt_at": None}, synchronize_session=False)
        db.query(AppointmentCalendarEvent).filter(
            AppointmentCalendarEvent.tenant_id == tenant_id, AppointmentCalendarEvent.state == "pending",
        ).update({"next_attempt_at": None}, synchronize_session=False)
        db.commit()
    finally:
        db.close()
    pushed = 0
    while True:
        batch = push_pending(tenant_id, limit=50)
        pushed += batch
        if batch < 50:
            break
    return {"pushed": pushed, "changed": pull_changes(tenant_id)}


# --- Busy times ----------------------------------------------------------------------------------

def external_busy(tenant_id: str, start_utc: str, end_utc: str) -> list[tuple[str, str]]:
    """Busy periods overlapping [start, end) in the workspace's connected calendars (UTC ISO strings)."""
    db = SessionLocal()
    try:
        conns = db.query(CalendarConnection).filter(CalendarConnection.tenant_id == tenant_id,
                                                    CalendarConnection.status == "active").all()
        periods: list[tuple[str, str]] = []
        for conn in conns:
            key = (conn.id, start_utc, end_utc)
            cached = _busy_cache.get(key)
            if cached and cached[0] > time.monotonic():
                periods += cached[1]
                continue
            impl = provider(conn.provider)
            try:
                found = _call(db, conn, lambda t: impl.busy(t, conn.calendar_id, conn.account_email, start_utc, end_utc,
                                                            conn.accounts_url))
            except Exception as exc:
                logger.warning("[CAL] %s busy times unavailable for %s: %s", conn.provider, tenant_id, exc)
                continue
            _busy_cache[key] = (time.monotonic() + BUSY_CACHE_SECONDS, found)
            periods += found
        return periods
    finally:
        db.close()


def busy_conflict(tenant_id: str, start_utc: str, end_utc: str, ignore: tuple[str, str] | None = None) -> bool:
    """True when a connected calendar is busy during [start, end). `ignore` is the appointment's own current
    slot when it is being moved (its own event shows as busy there)."""
    for s, e in external_busy(tenant_id, start_utc, end_utc):
        if ignore and (s, e) == ignore:
            continue
        if s < end_utc and e > start_utc:
            return True
    return False


# --- Worker --------------------------------------------------------------------------------------

_task: asyncio.Task | None = None


async def calendar_worker_loop() -> None:
    last_pull = 0.0
    while True:
        try:
            await asyncio.to_thread(push_pending)
            if time.monotonic() - last_pull >= PULL_SECONDS:
                last_pull = time.monotonic()
                await asyncio.to_thread(pull_changes)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("[CAL] Worker error: %s", exc)
        await asyncio.sleep(PUSH_SECONDS)


def start_calendar_worker() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(calendar_worker_loop())
