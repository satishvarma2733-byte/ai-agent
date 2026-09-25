from __future__ import annotations

import base64
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from supabase import Client, create_client

logger = logging.getLogger("db")

_SUPABASE_CLIENT: Client | None = None
_SUPABASE_CLIENT_KEY: tuple[str, str] | None = None

# DNS failure cooldown â€” only log once every 5 min to avoid log spam
_last_dns_warn: float = 0.0
_DNS_WARN_INTERVAL = 300.0  # seconds


def _is_dns_error(exc: Exception) -> bool:
    """Return True if the exception is a DNS / network-unreachable error."""
    msg = str(exc).lower()
    return any(k in msg for k in ("getaddrinfo", "11001", "name or service not known",
                                   "nodename nor servname", "network is unreachable"))


def _log_db_error(msg: str, exc: Exception) -> None:
    """Log DB errors, but throttle DNS-failure noise to once per 5 minutes."""
    global _last_dns_warn
    if _is_dns_error(exc):
        now = time.time()
        if now - _last_dns_warn > _DNS_WARN_INTERVAL:
            logger.warning(f"{msg} [DNS failure â€” Supabase unreachable, degraded mode]: {exc}")
            _last_dns_warn = now
        # else: silently swallow repeated DNS errors
    else:
        logger.error(f"{msg}: {exc}")

_ANALYTICS_COLUMNS = {
    "sentiment",
    "was_booked",
    "interrupt_count",
    "estimated_cost_usd",
    "call_date",
    "call_hour",
    "call_day_of_week",
}
_APPOINTMENT_COLUMNS = (
    "id, created_at, updated_at, title, contact_name, contact_phone, "
    "scheduled_start, scheduled_end, timezone, status, notes, source"
)
_APPOINTMENT_STATUSES = {"scheduled", "cancelled", "completed"}
_APPOINTMENT_SOURCES = {"voice_agent", "manual_ui", "backend_api"}
_IST = timezone(timedelta(hours=5, minutes=30))

_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0, 4.0]
_REQUIRED_SUPABASE_TABLES = (
    "call_logs",
    "call_transcripts",
    "active_calls",
    "appointments",
    "call_turn_metrics",
    "kb_sources",
    "kb_documents",
    "kb_chunks",
    "kb_ingest_jobs",
)


class AppointmentError(Exception):
    """Base error for appointments data operations."""


class AppointmentConflictError(AppointmentError):
    """Raised when an appointment overlaps an active appointment."""


class AppointmentNotFoundError(AppointmentError):
    """Raised when an appointment row does not exist."""


class AppointmentValidationError(AppointmentError):
    """Raised when appointment input is invalid."""


def _is_retryable(err_str: str) -> bool:
    transient = ("525", "ssl", "timeout", "connection", "network", "502", "503", "504")
    el = err_str.lower()
    return any(item in el for item in transient)


def _is_schema_error(err_str: str) -> bool:
    return "PGRST204" in err_str or "schema cache" in err_str.lower()


def _extract_missing_column(err_str: str) -> str | None:
    match = re.search(r"Could not find the '([^']+)' column", err_str, re.IGNORECASE)
    return match.group(1) if match else None


def _missing_appointments_table_message() -> str:
    return "Appointments table is missing. Run sql/supabase/setup.sql in Supabase."


def _parse_iso_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        clean = value.strip()
        if not clean:
            raise AppointmentValidationError("Appointment datetime is required.")
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(clean)
        except ValueError as exc:
            raise AppointmentValidationError(f"Invalid appointment datetime: {value}") from exc
    else:
        raise AppointmentValidationError("Appointment datetime must be a string or datetime.")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_IST)
    return dt


def _normalize_appointment_error(exc: Exception) -> AppointmentError:
    err = str(exc)
    if _is_schema_error(err):
        return AppointmentValidationError(_missing_appointments_table_message())
    if "appointments_no_overlap" in err or "23P01" in err or "overlap" in err.lower():
        return AppointmentConflictError("That time overlaps an existing scheduled appointment.")
    if "appointments_valid_status" in err:
        return AppointmentValidationError("Appointment status is invalid.")
    if "appointments_valid_source" in err:
        return AppointmentValidationError("Appointment source is invalid.")
    if "appointments_valid_window" in err or "scheduled_end" in err:
        return AppointmentValidationError("Appointment end time must be after start time.")
    return AppointmentError(err)


def _normalize_appointment_payload(
    payload: dict[str, Any],
    *,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    title = (payload.get("title") or "").strip() or (current or {}).get("title") or "Appointment"
    contact_name = (payload.get("contact_name") or (current or {}).get("contact_name") or "").strip()
    contact_phone = (payload.get("contact_phone") or (current or {}).get("contact_phone") or "").strip()
    notes = payload.get("notes")
    if notes is None:
        notes = (current or {}).get("notes") or ""
    notes = str(notes).strip()
    timezone_name = (
        (payload.get("timezone") or "").strip()
        or (current or {}).get("timezone")
        or "Asia/Kolkata"
    )
    status = (payload.get("status") or (current or {}).get("status") or "scheduled").strip().lower()
    source = (payload.get("source") or (current or {}).get("source") or "manual_ui").strip().lower()

    if status not in _APPOINTMENT_STATUSES:
        raise AppointmentValidationError(f"Unsupported appointment status: {status}")
    if source not in _APPOINTMENT_SOURCES:
        raise AppointmentValidationError(f"Unsupported appointment source: {source}")

    start_value = payload.get("scheduled_start", (current or {}).get("scheduled_start"))
    if not start_value:
        raise AppointmentValidationError("scheduled_start is required.")
    start_dt = _parse_iso_datetime(start_value)

    end_value = payload.get("scheduled_end")
    if end_value:
        end_dt = _parse_iso_datetime(end_value)
    elif current and "scheduled_start" in payload and "scheduled_end" not in payload:
        current_start = _parse_iso_datetime(current["scheduled_start"])
        current_end = _parse_iso_datetime(current["scheduled_end"])
        end_dt = start_dt + (current_end - current_start)
    else:
        fallback_end = (current or {}).get("scheduled_end")
        end_dt = _parse_iso_datetime(fallback_end) if fallback_end else start_dt + timedelta(minutes=30)

    if end_dt <= start_dt:
        raise AppointmentValidationError("scheduled_end must be after scheduled_start.")

    return {
        "title": title,
        "contact_name": contact_name,
        "contact_phone": contact_phone,
        "scheduled_start": start_dt.isoformat(),
        "scheduled_end": end_dt.isoformat(),
        "timezone": timezone_name,
        "status": status,
        "notes": notes,
        "source": source,
    }


def get_supabase() -> Client | None:
    url = str(os.environ.get("SUPABASE_URL", "") or "").strip()
    key = str(os.environ.get("SUPABASE_KEY", "") or "").strip()
    if not url or not key:
        return None

    global _SUPABASE_CLIENT, _SUPABASE_CLIENT_KEY
    client_key = (url, key)
    if _SUPABASE_CLIENT is not None and _SUPABASE_CLIENT_KEY == client_key:
        return _SUPABASE_CLIENT
    try:
        _SUPABASE_CLIENT = create_client(url, key)
        _SUPABASE_CLIENT_KEY = client_key
        return _SUPABASE_CLIENT
    except Exception as exc:
        logger.error(f"Failed to init Supabase client: {exc}")
        return None


def check_supabase_setup() -> dict[str, Any]:
    url = str(os.environ.get("SUPABASE_URL", "") or "").strip()
    key = str(os.environ.get("SUPABASE_KEY", "") or "").strip()
    missing_env = [name for name, value in (("SUPABASE_URL", url), ("SUPABASE_KEY", key)) if not value]
    if missing_env:
        return {
            "status": "not_configured",
            "message": "Set SUPABASE_URL and SUPABASE_KEY, then run sql/supabase/setup.sql once.",
            "missing_env": missing_env,
            "missing_tables": [],
            "schema_file": "sql/supabase/setup.sql",
            "tables": {},
        }

    supabase = get_supabase()
    if not supabase:
        return {
            "status": "error",
            "message": "Supabase client could not be initialized. Check the URL and key.",
            "missing_env": [],
            "missing_tables": [],
            "schema_file": "sql/supabase/setup.sql",
            "tables": {},
        }

    tables: dict[str, dict[str, Any]] = {}
    for table_name in _REQUIRED_SUPABASE_TABLES:
        try:
            supabase.table(table_name).select("*").limit(1).execute()
            tables[table_name] = {"ok": True}
        except Exception as exc:
            tables[table_name] = {"ok": False, "message": str(exc)}

    missing_tables = [name for name, result in tables.items() if not result.get("ok")]
    if missing_tables:
        return {
            "status": "setup_required",
            "message": "Run sql/supabase/setup.sql in the Supabase SQL Editor.",
            "missing_env": [],
            "missing_tables": missing_tables,
            "schema_file": "sql/supabase/setup.sql",
            "tables": tables,
        }

    return {
        "status": "ok",
        "message": "Supabase is configured and the required tables are reachable.",
        "missing_env": [],
        "missing_tables": [],
        "schema_file": "sql/supabase/setup.sql",
        "tables": tables,
    }


def normalize_phone_number(phone_number: str | None) -> str:
    raw = str(phone_number or "").strip()
    if raw.startswith("whatsapp:"):
        raw = raw.split(":", 1)[1].strip()
    if not raw:
        return ""
    if raw.startswith("+"):
        return raw
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return f"+{digits}"
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"
    return f"+{digits}"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_call_log(
    phone: str,
    duration: int,
    transcript: str,
    summary: str = "",
    recording_url: str = "",
    caller_name: str = "",
    sentiment: str = "unknown",
    estimated_cost_usd: float | None = None,
    call_date: str | None = None,
    call_hour: int | None = None,
    call_day_of_week: str | None = None,
    was_booked: bool = False,
    interrupt_count: int = 0,
    call_room_id: str = "",
    tenant_id: str | None = None,
    direction: str = "inbound",
    agent_id: str | None = None,
) -> dict:
    saved_locally = False
    try:
        from app.services.call_store import record_call_log, resolve_tenant_id

        record_call_log(
            call_room_id=call_room_id,
            phone=phone,
            tenant_id=resolve_tenant_id({"tenant_id": tenant_id}),
            direction=direction,
            agent_id=agent_id,
            duration_seconds=duration,
            transcript=transcript,
            summary=summary,
            recording_url=recording_url,
            caller_name=caller_name,
            sentiment=sentiment,
            was_booked=was_booked,
            interrupt_count=interrupt_count,
            estimated_cost_usd=estimated_cost_usd or 0.0,
            call_date=call_date,
            call_hour=call_hour,
            call_day_of_week=call_day_of_week,
        )
        logger.info(f"[DB-Local] Saved call log to application database: room {call_room_id}")
        saved_locally = True
    except Exception as e:
        logger.error(f"[DB-Local] Failed to save call log to application database: {e}")

    supabase = get_supabase()
    if not supabase:
        # The application database is the record of calls; Supabase is an optional copy.
        if saved_locally:
            return {"success": True, "message": "Saved to the application database"}
        logger.warning("Supabase not configured and the application database save failed -> %s %ss", phone, duration)
        return {"success": False, "message": "Call log was not saved"}

    full_data: dict[str, Any] = {
        "phone_number": phone,
        "duration_seconds": duration,
        "transcript": transcript,
        "summary": summary,
        "sentiment": sentiment,
        "was_booked": was_booked,
        "interrupt_count": interrupt_count,
    }
    if recording_url:
        full_data["recording_url"] = recording_url
    if caller_name:
        full_data["caller_name"] = caller_name
    if estimated_cost_usd is not None:
        full_data["estimated_cost_usd"] = estimated_cost_usd
    if call_date:
        full_data["call_date"] = call_date
    if call_hour is not None:
        full_data["call_hour"] = call_hour
    if call_day_of_week:
        full_data["call_day_of_week"] = call_day_of_week
    if call_room_id:
        full_data["call_room_id"] = call_room_id

    base_data: dict[str, Any] = {
        key: value for key, value in full_data.items() if key not in _ANALYTICS_COLUMNS
    }

    def _try_insert(data: dict[str, Any], label: str) -> dict:
        payload = dict(data)
        transient_attempt = 0
        stripped_columns: list[str] = []

        while payload:
            try:
                res = supabase.table("call_logs").insert(payload).execute()
                return {
                    "success": True,
                    "data": res.data,
                    "dropped_columns": stripped_columns,
                }
            except Exception as exc:
                err = str(exc)
                if _is_schema_error(err):
                    missing_col = _extract_missing_column(err)
                    if missing_col and missing_col in payload:
                        payload.pop(missing_col, None)
                        stripped_columns.append(missing_col)
                        continue
                    logger.error(f"Failed to save call log ({label}) due to schema mismatch: {exc}")
                    return {"success": False, "message": err, "dropped_columns": stripped_columns}
                if _is_retryable(err) and transient_attempt < _MAX_RETRIES:
                    delay = _RETRY_DELAYS[min(transient_attempt, len(_RETRY_DELAYS) - 1)]
                    transient_attempt += 1
                    time.sleep(delay)
                    continue
                logger.error(f"Failed to save call log ({label}): {exc}")
                return {"success": False, "message": err, "dropped_columns": stripped_columns}

        return {"success": False, "message": "No compatible columns left to insert"}

    result = _try_insert(full_data, "full")
    if result.get("success"):
        return result
    if _is_schema_error(str(result.get("message", ""))):
        return _try_insert(base_data, "base-fallback")
    return result


def fetch_call_logs(
    limit: int = 50,
    *,
    phone_number: str | None = None,
    call_room_id: str | None = None,
) -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return []
    for attempt in range(_MAX_RETRIES):
        try:
            query = supabase.table("call_logs").select("*").order("created_at", desc=True)
            if phone_number:
                query = query.eq("phone_number", normalize_phone_number(phone_number))
            if call_room_id:
                query = query.eq("call_room_id", str(call_room_id))
            if limit:
                query = query.limit(limit)
            res = query.execute()
            return res.data or []
        except Exception as exc:
            if _is_retryable(str(exc)) and attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAYS[attempt])
                continue
            _log_db_error("Failed to fetch call logs", exc)
            return []
    return []


def fetch_active_calls() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        res = supabase.table("active_calls").select("*").neq("status", "completed").execute()
        return res.data or []
    except Exception as exc:
        _log_db_error("Failed to fetch active calls", exc)
        return []


def fetch_inbound_calls(limit: int = 50) -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        # 1. Fetch active inbound calls
        active_res = supabase.table("active_calls").select("*").neq("status", "completed").execute()
        active_rows = active_res.data or []
        active_inbound = []
        for r in active_rows:
            room = r.get("room_id") or ""
            if room.startswith("call-inbound-"):
                started_str = r.get("started_at")
                duration = 0
                if started_str:
                    try:
                        clean_started = started_str.replace("Z", "+00:00")
                        started_dt = datetime.fromisoformat(clean_started)
                        duration = int((datetime.now(timezone.utc) - started_dt).total_seconds())
                    except Exception:
                        pass
                active_inbound.append({
                    "id": room,
                    "phone_number": r.get("phone") or "unknown",
                    "caller_name": r.get("caller_name") or "Unknown Caller",
                    "status": "live" if r.get("status") == "active" else "queued",
                    "started_at": started_str or _utcnow_iso(),
                    "duration_seconds": max(0, duration),
                    "sentiment": "unknown",
                    "room_id": room
                })
        
        # 2. Fetch completed inbound calls from call_logs
        logs_res = supabase.table("call_logs").select("*").order("created_at", desc=True).limit(limit * 2).execute()
        logs_rows = logs_res.data or []
        completed_inbound = []
        for r in logs_rows:
            room = r.get("call_room_id") or ""
            if room.startswith("call-inbound-"):
                completed_inbound.append({
                    "id": str(r.get("id")),
                    "phone_number": r.get("phone_number") or "unknown",
                    "caller_name": r.get("caller_name") or "Unknown Caller",
                    "status": "completed",
                    "started_at": r.get("created_at"),
                    "duration_seconds": r.get("duration_seconds") or 0,
                    "sentiment": r.get("sentiment") or "unknown",
                    "room_id": room,
                    "recording_url": r.get("recording_url") or f"/api/recordings/{room}.wav",
                    "summary": r.get("summary") or "No summary available."
                })
        
        combined = active_inbound + completed_inbound
        return combined[:limit]
    except Exception as exc:
        _log_db_error("Failed to fetch inbound calls", exc)
        return []


def fetch_outbound_calls(limit: int = 50) -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        # 1. Fetch active outbound calls
        active_res = supabase.table("active_calls").select("*").neq("status", "completed").execute()
        active_rows = active_res.data or []
        active_outbound = []
        for r in active_rows:
            room = r.get("room_id") or ""
            if room.startswith("call-") and not room.startswith("call-inbound-"):
                started_str = r.get("started_at")
                duration = 0
                if started_str:
                    try:
                        clean_started = started_str.replace("Z", "+00:00")
                        started_dt = datetime.fromisoformat(clean_started)
                        duration = int((datetime.now(timezone.utc) - started_dt).total_seconds())
                    except Exception:
                        pass
                active_outbound.append({
                    "id": room,
                    "phone_number": r.get("phone") or "unknown",
                    "caller_name": r.get("caller_name") or "Unknown Contact",
                    "status": "live" if r.get("status") == "active" else "queued",
                    "started_at": started_str or _utcnow_iso(),
                    "duration_seconds": max(0, duration),
                    "sentiment": "unknown",
                    "room_id": room
                })
        
        # 2. Fetch completed outbound calls from call_logs
        logs_res = supabase.table("call_logs").select("*").order("created_at", desc=True).limit(limit * 2).execute()
        logs_rows = logs_res.data or []
        completed_outbound = []
        for r in logs_rows:
            room = r.get("call_room_id") or ""
            if room.startswith("call-") and not room.startswith("call-inbound-"):
                completed_outbound.append({
                    "id": str(r.get("id")),
                    "phone_number": r.get("phone_number") or "unknown",
                    "caller_name": r.get("caller_name") or "Unknown Contact",
                    "status": "completed",
                    "started_at": r.get("created_at"),
                    "duration_seconds": r.get("duration_seconds") or 0,
                    "sentiment": r.get("sentiment") or "unknown",
                    "room_id": room,
                    "recording_url": r.get("recording_url") or f"/api/recordings/{room}.wav",
                    "summary": r.get("summary") or "No summary available."
                })
        
        combined = active_outbound + completed_outbound
        return combined[:limit]
    except Exception as exc:
        _log_db_error("Failed to fetch outbound calls", exc)
        return []


def get_call_log(log_id: str | int) -> dict[str, Any] | None:
    supabase = get_supabase()
    if not supabase:
        return None
    try:
        res = supabase.table("call_logs").select("*").eq("id", str(log_id)).single().execute()
        return res.data or None
    except Exception as exc:
        _log_db_error("Failed to fetch call log {log_id}", exc)
        return None


def save_call_transcript(call_room_id: str, phone: str, role: str, content: str) -> dict[str, Any] | None:
    supabase = get_supabase()
    if not supabase:
        return None
    row = {
        "call_room_id": str(call_room_id or "").strip(),
        "phone": normalize_phone_number(phone) or None,
        "role": str(role or "").strip().lower(),
        "content": str(content or "").strip(),
    }
    if row["role"] not in {"user", "assistant"} or not row["content"] or not row["call_room_id"]:
        return None
    try:
        res = supabase.table("call_transcripts").insert(row).execute()
        rows = res.data or []
        return rows[0] if rows else row
    except Exception as exc:
        if _is_schema_error(str(exc)):
            return None
        logger.debug(f"Failed to save call transcript: {exc}")
        return None


def list_call_transcripts(
    *,
    call_room_id: str | None = None,
    phone: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        query = supabase.table("call_transcripts").select("*").order("created_at")
        if call_room_id:
            query = query.eq("call_room_id", str(call_room_id))
        if phone:
            query = query.eq("phone", normalize_phone_number(phone))
        if limit:
            query = query.limit(limit)
        res = query.execute()
        return res.data or []
    except Exception as exc:
        if _is_schema_error(str(exc)):
            return []
        logger.debug(f"Failed to fetch call transcripts: {exc}")
        return []


def upsert_active_call(room_id: str, phone: str, caller_name: str, status: str) -> dict[str, Any] | None:
    supabase = get_supabase()
    if not supabase:
        return None
    payload = {
        "room_id": str(room_id or "").strip(),
        "phone": normalize_phone_number(phone) or None,
        "caller_name": str(caller_name or "").strip() or None,
        "status": str(status or "").strip() or "active",
        "last_updated": _utcnow_iso(),
    }
    if not payload["room_id"]:
        return None
    try:
        res = supabase.table("active_calls").upsert(payload).execute()
        rows = res.data or []
        return rows[0] if rows else payload
    except Exception as exc:
        if _is_schema_error(str(exc)):
            return None
        logger.debug(f"Failed to upsert active call: {exc}")
        return None


def fetch_appointments(
    *,
    start_iso: str | None = None,
    end_iso: str | None = None,
    statuses: list[str] | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        query = supabase.table("appointments").select(_APPOINTMENT_COLUMNS).order("scheduled_start")
        if start_iso:
            query = query.gt("scheduled_end", start_iso)
        if end_iso:
            query = query.lt("scheduled_start", end_iso)
        if statuses:
            cleaned = [status.strip().lower() for status in statuses if status.strip()]
            if cleaned:
                if len(cleaned) == 1:
                    query = query.eq("status", cleaned[0])
                else:
                    query = query.in_("status", cleaned)
        if limit:
            query = query.limit(limit)
        res = query.execute()
        return res.data or []
    except Exception as exc:
        if _is_dns_error(exc):
            _log_db_error("Failed to fetch appointments", exc)
            return []
        normalized = _normalize_appointment_error(exc)
        _log_db_error("Failed to fetch appointments", normalized)
        raise normalized


def get_appointment(appointment_id: str | int) -> dict[str, Any]:
    supabase = get_supabase()
    if not supabase:
        raise AppointmentValidationError("Supabase not configured.")
    try:
        res = (
            supabase.table("appointments")
            .select(_APPOINTMENT_COLUMNS)
            .eq("id", str(appointment_id))
            .single()
            .execute()
        )
        if not res.data:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found.")
        return res.data
    except AppointmentNotFoundError:
        raise
    except Exception as exc:
        if _is_dns_error(exc):
            _log_db_error(f"Failed to fetch appointment {appointment_id}", exc)
            raise AppointmentNotFoundError(f"Supabase unreachable — appointment {appointment_id} unavailable.")
        normalized = _normalize_appointment_error(exc)
        _log_db_error(f"Failed to fetch appointment {appointment_id}", normalized)
        raise normalized


def create_appointment(payload: dict[str, Any]) -> dict[str, Any]:
    supabase = get_supabase()
    if not supabase:
        raise AppointmentValidationError("Supabase not configured.")
    data = _normalize_appointment_payload(payload)
    try:
        res = supabase.table("appointments").insert(data).execute()
        if not res.data:
            raise AppointmentError("Appointment insert returned no data.")
        return res.data[0]
    except Exception as exc:
        normalized = _normalize_appointment_error(exc)
        logger.error(f"Failed to create appointment: {normalized}")
        raise normalized


def update_appointment(appointment_id: str | int, payload: dict[str, Any]) -> dict[str, Any]:
    supabase = get_supabase()
    if not supabase:
        raise AppointmentValidationError("Supabase not configured.")
    current = get_appointment(appointment_id)
    data = _normalize_appointment_payload(payload, current=current)
    try:
        res = (
            supabase.table("appointments")
            .update(data)
            .eq("id", str(appointment_id))
            .execute()
        )
        if not res.data:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found.")
        return res.data[0]
    except AppointmentNotFoundError:
        raise
    except Exception as exc:
        normalized = _normalize_appointment_error(exc)
        logger.error(f"Failed to update appointment {appointment_id}: {normalized}")
        raise normalized


def cancel_appointment(appointment_id: str | int, reason: str = "") -> dict[str, Any]:
    current = get_appointment(appointment_id)
    notes = (current.get("notes") or "").strip()
    reason = reason.strip()
    if reason:
        notes = f"{notes}\n\nCancellation reason: {reason}".strip()
    return update_appointment(appointment_id, {"status": "cancelled", "notes": notes})


def fetch_stats() -> dict[str, int]:
    empty = {"total_calls": 0, "total_bookings": 0, "avg_duration": 0, "booking_rate": 0}
    supabase = get_supabase()
    if not supabase:
        return empty
    try:
        rows = supabase.table("call_logs").select("duration_seconds, summary, was_booked").execute().data or []
        total = len(rows)
        bookings = sum(
            1 for row in rows if row.get("was_booked") or "confirmed" in (row.get("summary") or "").lower()
        )
        durations = [row["duration_seconds"] for row in rows if row.get("duration_seconds")]
        avg_duration = round(sum(durations) / len(durations)) if durations else 0
        booking_rate = round((bookings / total) * 100) if total else 0
        return {
            "total_calls": total,
            "total_bookings": bookings,
            "avg_duration": avg_duration,
            "booking_rate": booking_rate,
        }
    except Exception as exc:
        _log_db_error("Failed to fetch stats", exc)
        return empty


def save_call_turn_metric(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        from app.core.database import SessionLocal
        from app.models.call import CallTurnMetric as DB_CallTurnMetric, CallLog as DB_CallLog
        db_session = SessionLocal()
        try:
            tenant_id = None
            room_id = payload.get("call_room_id")
            if room_id:
                call_log = db_session.query(DB_CallLog).filter(DB_CallLog.call_room_id == room_id).first()
                if call_log:
                    tenant_id = call_log.tenant_id
            if not tenant_id:
                # Inbound calls get their call log only at hang-up; use the same tenant resolution.
                from app.services.call_store import resolve_tenant_id
                tenant_id = resolve_tenant_id({})
            if not tenant_id:
                logger.error(f"[DB-Local] Skipping turn metric for room {room_id}: no tenant. Set DEFAULT_TENANT_ID.")
                return None
            
            metric = DB_CallTurnMetric(
                call_room_id=payload.get("call_room_id"),
                phone_number=payload.get("phone_number"),
                turn_index=payload.get("turn_index", 0),
                speaker=payload.get("speaker", "assistant"),
                stt_endpoint_ms=payload.get("stt_endpoint_ms"),
                kb_ms=payload.get("kb_ms"),
                llm_first_token_ms=payload.get("llm_first_token_ms"),
                tts_first_audio_ms=payload.get("tts_first_audio_ms"),
                tool_ms=payload.get("tool_ms"),
                total_turn_ms=payload.get("total_turn_ms"),
                kb_used=payload.get("kb_used", False),
                kb_skipped_reason=payload.get("kb_skipped_reason"),
                metadata_json=str(payload.get("metadata") or payload.get("metadata_json") or ""),
                tenant_id=tenant_id
            )
            db_session.add(metric)
            db_session.commit()
            logger.info(f"[DB-Local] Saved call turn metric to SQLAlchemy database: room {room_id}")
        except Exception as e:
            logger.error(f"[DB-Local] Failed to save CallTurnMetric to local SQLAlchemy DB: {e}")
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"[DB-Local] Failed to import SessionLocal / CallTurnMetric: {e}")

    supabase = get_supabase()
    if not supabase:
        return None
    row = {
        "call_room_id": str(payload.get("call_room_id") or "").strip() or None,
        "phone_number": normalize_phone_number(payload.get("phone_number", "")) or None,
        "turn_index": int(payload.get("turn_index") or 0),
        "speaker": str(payload.get("speaker") or "assistant").strip().lower() or "assistant",
        "stt_endpoint_ms": payload.get("stt_endpoint_ms"),
        "kb_ms": payload.get("kb_ms"),
        "llm_first_token_ms": payload.get("llm_first_token_ms"),
        "tts_first_audio_ms": payload.get("tts_first_audio_ms"),
        "tool_ms": payload.get("tool_ms"),
        "total_turn_ms": payload.get("total_turn_ms"),
        "kb_used": bool(payload.get("kb_used", False)),
        "kb_skipped_reason": str(payload.get("kb_skipped_reason") or "").strip() or None,
        "metadata": payload.get("metadata") or {},
        "created_at": str(payload.get("created_at") or _utcnow_iso()),
    }
    try:
        res = supabase.table("call_turn_metrics").insert(row).execute()
        rows = res.data or []
        return rows[0] if rows else row
    except Exception as exc:
        if _is_schema_error(str(exc)):
            logger.warning("call_turn_metrics table is missing. Run sql/supabase/setup.sql.")
            return None
        logger.error(f"Failed to save call turn metric: {exc}")
        return None


def list_call_turn_metrics(
    *,
    call_room_id: str | None = None,
    phone_number: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        query = supabase.table("call_turn_metrics").select("*").order("created_at")
        if call_room_id:
            query = query.eq("call_room_id", str(call_room_id))
        if phone_number:
            query = query.eq("phone_number", normalize_phone_number(phone_number))
        if limit:
            query = query.limit(limit)
        res = query.execute()
        return res.data or []
    except Exception as exc:
        if _is_schema_error(str(exc)):
            return []
        _log_db_error("Failed to fetch call turn metrics", exc)
        return []


# â”€â”€â”€ CRM Lead Management Mock Storage & Functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import json

def _get_store_path(filename: str) -> str:
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, filename)

def _load_json_store(filename: str, default: Any) -> Any:
    path = _get_store_path(filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading store {filename}: {e}")
        return default

def _save_json_store(filename: str, data: Any) -> None:
    path = _get_store_path(filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving store {filename}: {e}")

_MOCK_LEADS = [
    {
        "id": "lead-1",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "name": "Satish Kumar",
        "phone": "+919000000001",
        "email": "satish.kumar@example.com",
        "company": "eWings Abroad",
        "status": "New",
        "score": "Hot",
        "score_explanation": "NEET qualified, good budget, and parents are highly involved in the decision process.",
        "assigned_agent": "Aryan",
        "state": "Telangana",
        "neet_score": 380,
        "rank": 184920,
        "budget": "20-25L",
        "parent_involved": True,
        "country_preference": "Kyrgyzstan",
        "follow_up_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d"),
        "objection": "Validity in India",
        "session_booked": False,
        "notes": "Student is interested in Kyrgyzstan. Parents have concerns about NMC regulations."
    },
    {
        "id": "lead-2",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "name": "Priyanka Reddy",
        "phone": "+919000000002",
        "email": "priyanka.reddy@example.com",
        "company": "eWings Abroad",
        "status": "Contacted",
        "score": "Hot",
        "score_explanation": "Wants premium European lifestyle and strong clinical exposure. High NEET score.",
        "assigned_agent": "Neha",
        "state": "Andhra Pradesh",
        "neet_score": 480,
        "rank": 94820,
        "budget": "25-35L",
        "parent_involved": True,
        "country_preference": "Georgia",
        "follow_up_date": (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d"),
        "objection": "Safety for girls",
        "session_booked": True,
        "notes": "Booked physical counseling session for next Sunday. Georgia is the main preference."
    },
    {
        "id": "lead-3",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "name": "Amit Sharma",
        "phone": "+919876543210",
        "email": "amit.sharma@example.com",
        "company": "eWings Abroad",
        "status": "Follow-up",
        "score": "Warm",
        "score_explanation": "Interested but researching multiple consultants. Parents not yet fully convinced.",
        "assigned_agent": "Aryan",
        "state": "Delhi",
        "neet_score": 280,
        "rank": 384012,
        "budget": "20-30L",
        "parent_involved": False,
        "country_preference": "Kazakhstan",
        "follow_up_date": (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d"),
        "objection": "Drop and repeat NEET",
        "session_booked": False,
        "notes": "Student wants to repeat NEET. Counselor is building urgency about losing another year."
    },
    {
        "id": "lead-4",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "name": "Rahul Verma",
        "phone": "+918765432109",
        "email": "rahul.v@example.com",
        "company": "eWings Abroad",
        "status": "Interested",
        "score": "Warm",
        "score_explanation": "Low NEET score but budget matches Uzbekistan packages perfectly.",
        "assigned_agent": "Unassigned",
        "state": "Uttar Pradesh",
        "neet_score": 120,
        "rank": 849201,
        "budget": "15-20L",
        "parent_involved": True,
        "country_preference": "Uzbekistan",
        "follow_up_date": (datetime.now(timezone.utc) + timedelta(days=4)).strftime("%Y-%m-%d"),
        "objection": "None",
        "session_booked": False,
        "notes": "Keen on Tashkent Medical Academy. Needs assistance with education loan documents."
    },
    {
        "id": "lead-5",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=6)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        "name": "Sneha Patil",
        "phone": "+917654321098",
        "email": "sneha.p@example.com",
        "company": "eWings Abroad",
        "status": "Lost",
        "score": "Cold",
        "score_explanation": "NEET not qualified and budget is too low (under 15 Lakhs).",
        "assigned_agent": "Neha",
        "state": "Maharashtra",
        "neet_score": 90,
        "rank": 1102948,
        "budget": "Under 15L",
        "parent_involved": False,
        "country_preference": "None",
        "follow_up_date": None,
        "objection": "Budget constraints",
        "session_booked": False,
        "notes": "Did not clear NEET. Closed lead."
    }
]

_MOCK_TIMELINE = {
    "lead-1": [
        {"id": "act-1", "created_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "activity_type": "crm_update", "title": "Lead Created", "description": "Lead created via website inquiry form.", "metadata": {}},
        {"id": "act-2", "created_at": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(), "activity_type": "note", "title": "Added Counselor Note", "description": "Spoke to student. He is very keen but father wants details about validation of Kyrgyzstan MBBS degree in India.", "metadata": {}},
    ],
    "lead-2": [
        {"id": "act-3", "created_at": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(), "activity_type": "crm_update", "title": "Lead Created", "description": "Lead created via Facebook lead form.", "metadata": {}},
        {"id": "act-4", "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(), "activity_type": "call", "title": "AI Outbound Call Complete", "description": "Duration: 1m 24s. Sentiment: Positive. Student responded well to Georgia clinical exposure.", "metadata": {"duration": 84, "sentiment": "positive", "was_booked": True}},
        {"id": "act-5", "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(), "activity_type": "whatsapp", "title": "WhatsApp Day 0 Sent", "description": "eWings welcome template dispatched containing Georgia details.", "metadata": {}},
    ]
}

_MOCK_WORKFLOWS = [
    {
        "id": "wf-1",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        "name": "New Lead Automated AI Outbound Call",
        "trigger_event": "lead_created",
        "actions": [
            {"type": "ai_call", "config": {"delay_seconds": 5}},
            {"type": "crm_update", "config": {"status": "Contacted"}}
        ],
        "is_active": True
    },
    {
        "id": "wf-2",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        "name": "Post-Call WhatsApp Follow-up",
        "trigger_event": "call_ended",
        "actions": [
            {"type": "whatsapp", "config": {"template": "day_0_intro"}},
            {"type": "reminder", "config": {"title": "Follow up with parents", "delay_days": 1}}
        ],
        "is_active": True
    }
]

def init_crm_mock_store():
    global _MOCK_LEADS, _MOCK_TIMELINE, _MOCK_WORKFLOWS
    _MOCK_LEADS = _load_json_store("crm_leads.json", _MOCK_LEADS)
    _MOCK_TIMELINE = _load_json_store("crm_timeline.json", _MOCK_TIMELINE)
    _MOCK_WORKFLOWS = _load_json_store("crm_workflows.json", _MOCK_WORKFLOWS)
    
    # Write back to file to ensure files exist on disk
    _save_json_store("crm_leads.json", _MOCK_LEADS)
    _save_json_store("crm_timeline.json", _MOCK_TIMELINE)
    _save_json_store("crm_workflows.json", _MOCK_WORKFLOWS)

init_crm_mock_store()

def fetch_leads() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_LEADS
    try:
        res = supabase.table("crm_leads").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase crm_leads fetch failed, falling back to mock: {exc}")
        return _MOCK_LEADS

def save_lead(lead: dict[str, Any]) -> dict[str, Any]:
    lead_id = lead.get("id")
    lead["phone"] = normalize_phone_number(lead.get("phone") or "")
    if not lead["phone"]:
        raise ValueError("Phone number is required.")
    lead["phone_encrypted"] = encrypt_phone(lead["phone"])

    supabase = get_supabase()
    lead["updated_at"] = _utcnow_iso()
    
    if supabase:
        try:
            if lead_id:
                res = supabase.table("crm_leads").update(lead).eq("id", str(lead_id)).execute()
            else:
                lead["created_at"] = _utcnow_iso()
                res = supabase.table("crm_leads").insert(lead).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase crm_leads save failed, falling back to mock: {exc}")

    # Fallback Mock Logic
    import uuid
    if lead_id:
        for idx, item in enumerate(_MOCK_LEADS):
            if str(item["id"]) == str(lead_id):
                _MOCK_LEADS[idx].update(lead)
                _save_json_store("crm_leads.json", _MOCK_LEADS)
                return _MOCK_LEADS[idx]
    else:
        new_lead = dict(lead)
        new_lead["id"] = f"lead-{uuid.uuid4().hex[:8]}"
        new_lead["created_at"] = _utcnow_iso()
        _MOCK_LEADS.insert(0, new_lead)
        _save_json_store("crm_leads.json", _MOCK_LEADS)
        return new_lead
    return lead

def delete_lead(lead_id: str | int) -> bool:
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("crm_leads").delete().eq("id", str(lead_id)).execute()
            return True
        except Exception as exc:
            logger.debug(f"Supabase crm_leads delete failed, falling back to mock: {exc}")
            
    global _MOCK_LEADS
    original_len = len(_MOCK_LEADS)
    _MOCK_LEADS = [item for item in _MOCK_LEADS if str(item["id"]) != str(lead_id)]
    _save_json_store("crm_leads.json", _MOCK_LEADS)
    return len(_MOCK_LEADS) < original_len

def fetch_lead_timeline(lead_id: str | int) -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_TIMELINE.get(str(lead_id), [])
    try:
        res = supabase.table("crm_lead_activity").select("*").eq("lead_id", str(lead_id)).order("created_at", desc=True).execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase timeline fetch failed, falling back to mock: {exc}")
        return _MOCK_TIMELINE.get(str(lead_id), [])

def add_lead_activity(
    lead_id: str | int,
    activity_type: str,
    title: str,
    description: str = "",
    metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = {
        "lead_id": str(lead_id),
        "activity_type": activity_type,
        "title": title,
        "description": description,
        "metadata": metadata or {},
        "created_at": _utcnow_iso()
    }
    
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("crm_lead_activity").insert(payload).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase timeline insert failed, falling back to mock: {exc}")
            
    import uuid
    payload["id"] = f"act-{uuid.uuid4().hex[:8]}"
    timeline = _MOCK_TIMELINE.setdefault(str(lead_id), [])
    timeline.insert(0, payload)
    _save_json_store("crm_timeline.json", _MOCK_TIMELINE)
    return payload

def fetch_workflows() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_WORKFLOWS
    try:
        res = supabase.table("crm_workflows").select("*").order("created_at").execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase workflows fetch failed: {exc}")
        return _MOCK_WORKFLOWS

def save_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    wf_id = workflow.get("id")
    supabase = get_supabase()
    if supabase:
        try:
            if wf_id:
                res = supabase.table("crm_workflows").update(workflow).eq("id", str(wf_id)).execute()
            else:
                res = supabase.table("crm_workflows").insert(workflow).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase workflow save failed: {exc}")
            
    import uuid
    if wf_id:
        for idx, item in enumerate(_MOCK_WORKFLOWS):
            if str(item["id"]) == str(wf_id):
                _MOCK_WORKFLOWS[idx].update(workflow)
                _save_json_store("crm_workflows.json", _MOCK_WORKFLOWS)
                return _MOCK_WORKFLOWS[idx]
    else:
        new_wf = dict(workflow)
        new_wf["id"] = f"wf-{uuid.uuid4().hex[:8]}"
        new_wf["created_at"] = _utcnow_iso()
        _MOCK_WORKFLOWS.append(new_wf)
        _save_json_store("crm_workflows.json", _MOCK_WORKFLOWS)
        return new_wf
    return workflow

def delete_workflow(wf_id: str | int) -> bool:
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("crm_workflows").delete().eq("id", str(wf_id)).execute()
            return True
        except Exception as exc:
            logger.debug(f"Supabase workflow delete failed: {exc}")
            
    global _MOCK_WORKFLOWS
    orig_len = len(_MOCK_WORKFLOWS)
    _MOCK_WORKFLOWS = [w for w in _MOCK_WORKFLOWS if str(w["id"]) != str(wf_id)]
    _save_json_store("crm_workflows.json", _MOCK_WORKFLOWS)
    return len(_MOCK_WORKFLOWS) < orig_len


# â”€â”€â”€ CMS Data Storage & Fallback Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_MOCK_CMS_PAGES = [
    { "id": "1", "created_at": _utcnow_iso(), "updated_at": _utcnow_iso(), "title": "Homepage Hero", "slug": "hero", "status": "published", "category": "Marketing", "content": "Welcome to eWings Abroad..." },
    { "id": "2", "created_at": _utcnow_iso(), "updated_at": _utcnow_iso(), "title": "Pricing Page", "slug": "pricing", "status": "draft", "category": "Sales", "content": "Affordable packages starting from..." },
    { "id": "3", "created_at": _utcnow_iso(), "updated_at": _utcnow_iso(), "title": "About Us", "slug": "about", "status": "published", "category": "Corporate", "content": "We are a premium medical abroad consultant..." }
]

_MOCK_CMS_PROMPTS = [
    { "id": "1", "created_at": _utcnow_iso(), "updated_at": _utcnow_iso(), "name": "Primary Receptionist", "content": "You are Aria, a professional AI receptionist for eWings Abroad. Your job is to welcome students, answer general queries about MBBS options, and ask if they want to book a detailed session.", "active": True, "tags": ["inbound", "receptionist"] },
    { "id": "2", "created_at": _utcnow_iso(), "updated_at": _utcnow_iso(), "name": "Appointment Booking", "content": "You are Nexus, an AI assistant focused on booking appointments for medical abroad consultancy. You verify NEET score, budget, and parents' involvement, and then schedule details.", "active": False, "tags": ["booking", "outbound"] },
    { "id": "3", "created_at": _utcnow_iso(), "updated_at": _utcnow_iso(), "name": "Customer Support", "content": "You are Lyra, a helpful customer support AI. You resolve objections regarding NMC guidelines and course duration.", "active": False, "tags": ["support"] }
]

_MOCK_CMS_FAQS = [
    { "id": "1", "question": "What are your business hours?", "answer": "We are open Mondayâ€“Friday, 9amâ€“6pm IST.", "category": "General" },
    { "id": "2", "question": "How do I book an appointment?", "answer": "You can book an appointment by calling us or using our website.", "category": "Booking" },
    { "id": "3", "question": "Do you offer refunds?", "answer": "Yes, we offer a 30-day satisfaction guarantee on documentation processing.", "category": "Policies" }
]

_MOCK_CMS_MEDIA = []

def init_cms_mock_store():
    global _MOCK_CMS_PAGES, _MOCK_CMS_PROMPTS, _MOCK_CMS_FAQS, _MOCK_CMS_MEDIA
    loaded = _load_json_store("cms_store.json", {})
    _MOCK_CMS_PAGES = loaded.get("pages", _MOCK_CMS_PAGES)
    _MOCK_CMS_PROMPTS = loaded.get("prompts", _MOCK_CMS_PROMPTS)
    _MOCK_CMS_FAQS = loaded.get("faqs", _MOCK_CMS_FAQS)
    _MOCK_CMS_MEDIA = loaded.get("media", _MOCK_CMS_MEDIA)
    _save_cms_store()

def _save_cms_store():
    _save_json_store("cms_store.json", {
        "pages": _MOCK_CMS_PAGES,
        "prompts": _MOCK_CMS_PROMPTS,
        "faqs": _MOCK_CMS_FAQS,
        "media": _MOCK_CMS_MEDIA
    })

init_cms_mock_store()

def fetch_cms_pages() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_CMS_PAGES
    try:
        res = supabase.table("cms_pages").select("*").order("updated_at", desc=True).execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase cms_pages fetch failed, falling back to mock: {exc}")
        return _MOCK_CMS_PAGES

def save_cms_page(page: dict[str, Any]) -> dict[str, Any]:
    page_id = page.get("id")
    supabase = get_supabase()
    page["updated_at"] = _utcnow_iso()
    if supabase:
        try:
            if page_id:
                res = supabase.table("cms_pages").update(page).eq("id", str(page_id)).execute()
            else:
                page["created_at"] = _utcnow_iso()
                res = supabase.table("cms_pages").insert(page).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase cms_pages save failed, falling back to mock: {exc}")
    import uuid
    if page_id:
        for idx, item in enumerate(_MOCK_CMS_PAGES):
            if str(item["id"]) == str(page_id):
                _MOCK_CMS_PAGES[idx].update(page)
                _save_cms_store()
                return _MOCK_CMS_PAGES[idx]
    else:
        new_page = dict(page)
        new_page["id"] = str(uuid.uuid4())
        new_page["created_at"] = _utcnow_iso()
        _MOCK_CMS_PAGES.insert(0, new_page)
        _save_cms_store()
        return new_page
    return page

def delete_cms_page(page_id: str) -> bool:
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("cms_pages").delete().eq("id", str(page_id)).execute()
            return True
        except Exception as exc:
            logger.debug(f"Supabase cms_pages delete failed, falling back to mock: {exc}")
    global _MOCK_CMS_PAGES
    original_len = len(_MOCK_CMS_PAGES)
    _MOCK_CMS_PAGES = [item for item in _MOCK_CMS_PAGES if str(item["id"]) != str(page_id)]
    _save_cms_store()
    return len(_MOCK_CMS_PAGES) < original_len

def fetch_cms_prompts() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_CMS_PROMPTS
    try:
        res = supabase.table("cms_prompts").select("*").order("updated_at", desc=True).execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase cms_prompts fetch failed, falling back to mock: {exc}")
        return _MOCK_CMS_PROMPTS

def save_cms_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
    prompt_id = prompt.get("id")
    supabase = get_supabase()
    prompt["updated_at"] = _utcnow_iso()
    if supabase:
        try:
            if prompt_id:
                res = supabase.table("cms_prompts").update(prompt).eq("id", str(prompt_id)).execute()
            else:
                prompt["created_at"] = _utcnow_iso()
                res = supabase.table("cms_prompts").insert(prompt).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase cms_prompts save failed, falling back to mock: {exc}")
    import uuid
    if prompt_id:
        for idx, item in enumerate(_MOCK_CMS_PROMPTS):
            if str(item["id"]) == str(prompt_id):
                _MOCK_CMS_PROMPTS[idx].update(prompt)
                _save_cms_store()
                return _MOCK_CMS_PROMPTS[idx]
    else:
        new_prompt = dict(prompt)
        new_prompt["id"] = str(uuid.uuid4())
        new_prompt["created_at"] = _utcnow_iso()
        _MOCK_CMS_PROMPTS.insert(0, new_prompt)
        _save_cms_store()
        return new_prompt
    return prompt

def fetch_cms_faqs() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_CMS_FAQS
    try:
        res = supabase.table("cms_faqs").select("*").order("question").execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase cms_faqs fetch failed, falling back to mock: {exc}")
        return _MOCK_CMS_FAQS

def save_cms_faq(faq: dict[str, Any]) -> dict[str, Any]:
    faq_id = faq.get("id")
    supabase = get_supabase()
    if supabase:
        try:
            if faq_id:
                res = supabase.table("cms_faqs").update(faq).eq("id", str(faq_id)).execute()
            else:
                res = supabase.table("cms_faqs").insert(faq).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase cms_faqs save failed, falling back to mock: {exc}")
    import uuid
    if faq_id:
        for idx, item in enumerate(_MOCK_CMS_FAQS):
            if str(item["id"]) == str(faq_id):
                _MOCK_CMS_FAQS[idx].update(faq)
                _save_cms_store()
                return _MOCK_CMS_FAQS[idx]
    else:
        new_faq = dict(faq)
        new_faq["id"] = str(uuid.uuid4())
        _MOCK_CMS_FAQS.append(new_faq)
        _save_cms_store()
        return new_faq
    return faq

def delete_cms_faq(faq_id: str) -> bool:
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("cms_faqs").delete().eq("id", str(faq_id)).execute()
            return True
        except Exception as exc:
            logger.debug(f"Supabase cms_faqs delete failed, falling back to mock: {exc}")
    global _MOCK_CMS_FAQS
    original_len = len(_MOCK_CMS_FAQS)
    _MOCK_CMS_FAQS = [item for item in _MOCK_CMS_FAQS if str(item["id"]) != str(faq_id)]
    _save_cms_store()
    return len(_MOCK_CMS_FAQS) < original_len

def fetch_cms_media() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_CMS_MEDIA
    try:
        res = supabase.table("cms_media").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase cms_media fetch failed, falling back to mock: {exc}")
        return _MOCK_CMS_MEDIA

def save_cms_media(media: dict[str, Any]) -> dict[str, Any]:
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("cms_media").insert(media).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase cms_media insert failed: {exc}")
    _MOCK_CMS_MEDIA.insert(0, media)
    _save_cms_store()
    return media


# â”€â”€â”€ Agents Data Storage & Fallback Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_MOCK_AGENTS = [
    {
        "id": "agent-1",
        "name": "Aria",
        "status": "active",
        "voice": "Puck",
        "model": "gemini-2.0-flash-live-001",
        "calls_today": 5,
        "calls_total": 48,
        "avg_duration": 110,
        "success_rate": 82,
        "last_active": _utcnow_iso(),
        "description": "AI voice agent specialized in general inbound receptions and welcome queries.",
        "tags": ["inbound", "gemini-live", "kb-enabled"],
        "instructions": "You are Aria, a friendly medical abroad receptionist. Guide students to book counseling.",
        "temperature": 0.7
    },
    {
        "id": "agent-2",
        "name": "Nexus",
        "status": "processing",
        "voice": "Charon",
        "model": "gemini-2.5-flash",
        "calls_today": 3,
        "calls_total": 29,
        "avg_duration": 95,
        "success_rate": 78,
        "last_active": _utcnow_iso(),
        "description": "AI agent specialized in outbound lead qualification and budget discussions.",
        "tags": ["outbound", "gemini-live", "direct"],
        "instructions": "You are Nexus, an outbound lead qualification agent. Check budget, NEET score, and parent involvement.",
        "temperature": 0.5
    },
    {
        "id": "agent-3",
        "name": "Lyra",
        "status": "idle",
        "voice": "Kore",
        "model": "gemini-2.0-flash-live-001",
        "calls_today": 12,
        "calls_total": 140,
        "avg_duration": 130,
        "success_rate": 89,
        "last_active": _utcnow_iso(),
        "description": "AI specialist addressing objections regarding NMC guidelines.",
        "tags": ["inbound", "gemini-live", "kb-enabled"],
        "instructions": "You are Lyra, the NMC compliance specialist. Address concerns about course duration, license validation, and safety.",
        "temperature": 0.6
    }
]

def init_agents_mock_store():
    global _MOCK_AGENTS
    _MOCK_AGENTS = _load_json_store("agents_store.json", _MOCK_AGENTS)
    _save_json_store("agents_store.json", _MOCK_AGENTS)

init_agents_mock_store()

def fetch_agents() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_AGENTS
    try:
        res = supabase.table("agents").select("*").order("name").execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase agents fetch failed, falling back to mock: {exc}")
        return _MOCK_AGENTS

def save_agent(agent: dict[str, Any]) -> dict[str, Any]:
    agent_id = agent.get("id")
    supabase = get_supabase()
    if supabase:
        try:
            if agent_id:
                res = supabase.table("agents").update(agent).eq("id", str(agent_id)).execute()
            else:
                res = supabase.table("agents").insert(agent).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase agents save failed, falling back to mock: {exc}")
    import uuid
    if agent_id:
        for idx, item in enumerate(_MOCK_AGENTS):
            if str(item["id"]) == str(agent_id):
                _MOCK_AGENTS[idx].update(agent)
                _save_json_store("agents_store.json", _MOCK_AGENTS)
                return _MOCK_AGENTS[idx]
    else:
        new_agent = dict(agent)
        new_agent["id"] = f"agent-{uuid.uuid4().hex[:8]}"
        new_agent["calls_today"] = 0
        new_agent["calls_total"] = 0
        new_agent["avg_duration"] = 0
        new_agent["success_rate"] = 0
        new_agent["last_active"] = None
        _MOCK_AGENTS.append(new_agent)
        _save_json_store("agents_store.json", _MOCK_AGENTS)
        return new_agent
    return agent

def delete_agent(agent_id: str) -> bool:
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("agents").delete().eq("id", str(agent_id)).execute()
            return True
        except Exception as exc:
            logger.debug(f"Supabase agents delete failed, falling back to mock: {exc}")
    global _MOCK_AGENTS
    original_len = len(_MOCK_AGENTS)
    _MOCK_AGENTS = [item for item in _MOCK_AGENTS if str(item["id"]) != str(agent_id)]
    _save_json_store("agents_store.json", _MOCK_AGENTS)
    return len(_MOCK_AGENTS) < original_len


# â”€â”€â”€ Phone Number Encryption Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_FERNET: Fernet | None = None

def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    key = os.environ.get("ENCRYPTION_KEY", "")
    try:
        if not key:
            # Fallback static key for local development
            key = base64.urlsafe_b64encode(b"aVn-Voice-CRM-Default-Encryption")
        elif len(key) != 44:
            key = base64.urlsafe_b64encode(key.encode("utf-8")[:32].ljust(32, b"a"))
        _FERNET = Fernet(key)
    except Exception as exc:
        logger.warning(f"Failed to init Fernet: {exc}. Using random fallback.")
        _FERNET = Fernet(Fernet.generate_key())
    return _FERNET

def encrypt_phone(phone: str) -> str:
    if not phone:
        return ""
    try:
        f = _get_fernet()
        return f.encrypt(phone.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.error(f"Phone encryption error: {exc}")
        return phone

def decrypt_phone(encrypted_phone: str) -> str:
    if not encrypted_phone:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(encrypted_phone.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.debug(f"Phone decryption error: {exc}. Returning raw string.")
        return encrypted_phone


# â”€â”€â”€ Campaigns Data Storage & Fallback Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_MOCK_CAMPAIGNS: list[dict[str, Any]] = [
    {
        "id": "campaign-1",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "name": "NEET Admissions Outbound Inquiries",
        "status": "queued",
        "agent_id": "agent-2",
        "concurrency_limit": 3,
        "retry_limit": 1,
        "retry_delay_seconds": 1800
    }
]

def init_campaigns_mock_store():
    global _MOCK_CAMPAIGNS
    _MOCK_CAMPAIGNS = _load_json_store("crm_campaigns.json", _MOCK_CAMPAIGNS)
    _save_json_store("crm_campaigns.json", _MOCK_CAMPAIGNS)

init_campaigns_mock_store()

def fetch_campaigns() -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return _MOCK_CAMPAIGNS
    try:
        res = supabase.table("crm_campaigns").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as exc:
        logger.debug(f"Supabase crm_campaigns fetch failed: {exc}")
        return _MOCK_CAMPAIGNS

def save_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    campaign_id = campaign.get("id")
    supabase = get_supabase()
    campaign["updated_at"] = _utcnow_iso()
    
    if supabase:
        try:
            if campaign_id:
                res = supabase.table("crm_campaigns").update(campaign).eq("id", str(campaign_id)).execute()
            else:
                campaign["created_at"] = _utcnow_iso()
                res = supabase.table("crm_campaigns").insert(campaign).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            logger.debug(f"Supabase crm_campaigns save failed: {exc}")

    import uuid
    if campaign_id:
        for idx, item in enumerate(_MOCK_CAMPAIGNS):
            if str(item["id"]) == str(campaign_id):
                _MOCK_CAMPAIGNS[idx].update(campaign)
                _save_json_store("crm_campaigns.json", _MOCK_CAMPAIGNS)
                return _MOCK_CAMPAIGNS[idx]
    else:
        new_campaign = dict(campaign)
        new_campaign["id"] = f"campaign-{uuid.uuid4().hex[:8]}"
        new_campaign["created_at"] = _utcnow_iso()
        _MOCK_CAMPAIGNS.append(new_campaign)
        _save_json_store("crm_campaigns.json", _MOCK_CAMPAIGNS)
        return new_campaign
    return campaign

def delete_campaign(campaign_id: str) -> bool:
    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("crm_campaigns").delete().eq("id", str(campaign_id)).execute()
            return True
        except Exception as exc:
            logger.debug(f"Supabase crm_campaigns delete failed: {exc}")
    global _MOCK_CAMPAIGNS
    original_len = len(_MOCK_CAMPAIGNS)
    _MOCK_CAMPAIGNS = [item for item in _MOCK_CAMPAIGNS if str(item["id"]) != str(campaign_id)]
    _save_json_store("crm_campaigns.json", _MOCK_CAMPAIGNS)
    return len(_MOCK_CAMPAIGNS) < original_len

def fetch_campaign_leads(campaign_id: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    if not supabase:
        return [l for l in _MOCK_LEADS if l.get("campaign_id") == campaign_id]
    try:
        res = supabase.table("crm_leads").select("*").eq("campaign_id", str(campaign_id)).order("created_at").execute()
        leads = res.data or []
        for lead in leads:
            if lead.get("phone_encrypted"):
                lead["phone"] = decrypt_phone(lead["phone_encrypted"])
        return leads
    except Exception as exc:
        logger.debug(f"Supabase campaign leads fetch failed: {exc}")
        return [l for l in _MOCK_LEADS if l.get("campaign_id") == campaign_id]

def update_campaign_lead_status(
    lead_id: str,
    campaign_status: str,
    campaign_outcome: str | None = None,
    custom_fields: dict | None = None
) -> dict[str, Any] | None:
    supabase = get_supabase()
    update_data = {
        "campaign_status": campaign_status,
        "updated_at": _utcnow_iso()
    }
    if campaign_outcome is not None:
        update_data["campaign_outcome"] = campaign_outcome
    if custom_fields is not None:
        update_data["custom_fields"] = custom_fields

    if supabase:
        try:
            res = supabase.table("crm_leads").update(update_data).eq("id", str(lead_id)).execute()
            if res.data:
                lead = res.data[0]
                if lead.get("phone_encrypted"):
                    lead["phone"] = decrypt_phone(lead["phone_encrypted"])
                return lead
        except Exception as exc:
            logger.debug(f"Supabase lead campaign status update failed: {exc}")

    # Fallback to local mock array
    for idx, item in enumerate(_MOCK_LEADS):
        if str(item["id"]) == str(lead_id):
            _MOCK_LEADS[idx].update(update_data)
            _save_json_store("crm_leads.json", _MOCK_LEADS)
            return _MOCK_LEADS[idx]
    return None


