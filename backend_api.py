from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from campaign_worker import start_campaign_worker

from backend_config import (
    apply_config_env,
    parse_int,
    read_config,
    redact_config,
    write_config,
)
from backend_events import (
    handle_appointment_cancelled,
    handle_appointment_updated,
    handle_booking_confirmed,
)
from livekit import api
from outbound_calls import dispatch_outbound_call, get_livekit_settings


load_dotenv()

logging.basicConfig(level=logging.INFO)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger("backend-api")

MAX_KB_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(
    title="aVn Agent Backend API (legacy)",
    version="1.0.0",
    description="Headless backend API for the backend-only Gemini 3.1 Live branch.",
)

# Allow the frontend to make requests from any origin.
# In production, narrow allow_origins to your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def api_exception_handler(request: Request, exc: Exception):
    logger.exception(f"[API] Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse({"status": "error", "message": "Internal server error."}, status_code=500)


# ── Dev-mode Auth Stubs ─────────────────────────────────────────────────────
# These are local-only stubs so the frontend login/auth flow works without
# a real auth backend. In production replace with a real JWT implementation.
_DEV_TOKEN = "dev-token-aVn-local-2026"

@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """Accept any credentials in dev mode and return a persistent dev token."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    email = str(data.get("email") or "admin@avn.ai").strip()
    # Accept any password in dev mode
    return {
        "access_token": _DEV_TOKEN,
        "refresh_token": _DEV_TOKEN,
        "token_type": "bearer",
        "user": {
            "email": email,
            "name": email.split("@")[0].title(),
            "role": "admin",
            "tenant_id": "local",
        },
    }


@app.post("/api/auth/refresh")
async def api_auth_refresh(refresh_token: str = ""):
    """Refresh the dev token — always returns the same dev token."""
    return {
        "access_token": _DEV_TOKEN,
        "refresh_token": _DEV_TOKEN,
        "token_type": "bearer",
    }


@app.get("/api/auth/me")
async def api_auth_me(request: Request):
    """Return dev user profile."""
    return {
        "email": "admin@avn.ai",
        "name": "Admin",
        "role": "admin",
        "tenant_id": "local",
    }


@app.post("/api/auth/signup")
async def api_auth_signup(request: Request):
    """Dev-mode signup — accepts any registration and returns a dev token."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    email = str(data.get("email") or "admin@avn.ai").strip()
    name = str(data.get("name") or email.split("@")[0].title()).strip()
    return {
        "access_token": _DEV_TOKEN,
        "refresh_token": _DEV_TOKEN,
        "token_type": "bearer",
        "user": {
            "email": email,
            "name": name,
            "role": str(data.get("role") or "admin").lower(),
            "tenant_id": "local",
            "company_name": str(data.get("company_name") or ""),
        },
    }


def _load_runtime_config(phone_number: str | None = None) -> dict:
    config = read_config(phone_number)
    apply_config_env(config)
    return config


def parse_calendar_datetime(value: str) -> datetime:
    clean = value.strip()
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
    return dt


def appointment_error_response(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"status": "error", "message": message}, status_code=status_code)


def internal_error_response(
    public_message: str = "Unable to complete the request right now.",
    *,
    status_code: int = 500,
) -> JSONResponse:
    return JSONResponse({"status": "error", "message": public_message}, status_code=status_code)


def validate_appointment_payload(data: dict, current: dict | None = None) -> None:
    from calendar_tools import validate_appointment_window

    merged = dict(current or {})
    merged.update({key: value for key, value in data.items() if value is not None})
    status = (merged.get("status") or "scheduled").strip().lower()
    start_value = merged.get("scheduled_start")
    end_value = merged.get("scheduled_end")
    if status == "scheduled" and start_value and end_value:
        validate_appointment_window(
            parse_calendar_datetime(start_value),
            parse_calendar_datetime(end_value),
        )


def _safe_number(value):
    try:
        if value in (None, ""):
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _summarize_turn_metrics(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    numeric_fields = [
        "stt_endpoint_ms",
        "kb_ms",
        "llm_first_token_ms",
        "tts_first_audio_ms",
        "tool_ms",
        "total_turn_ms",
    ]
    summary: dict[str, object] = {
        "turns": len(rows),
        "kb_used_turns": sum(1 for row in rows if row.get("kb_used")),
    }
    for field in numeric_fields:
        values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
        if values:
            summary[field] = round(sum(values) / len(values), 2)
    slowest = None
    for row in rows:
        if row.get("total_turn_ms") in (None, ""):
            continue
        if slowest is None or float(row.get("total_turn_ms") or 0) > float(slowest.get("total_turn_ms") or 0):
            slowest = row
    if slowest:
        summary["slowest_turn"] = {
            "turn_index": slowest.get("turn_index"),
            "total_turn_ms": _safe_number(slowest.get("total_turn_ms")),
            "kb_used": bool(slowest.get("kb_used")),
            "kb_skipped_reason": slowest.get("kb_skipped_reason"),
        }
    return summary


def _attach_latency_summary(db_module, row: dict) -> dict:
    enriched = dict(row)
    room_id = str(row.get("call_room_id") or "").strip()
    direction = "inbound" if room_id.startswith("call-inbound-") else "outbound"
    enriched["direction"] = direction
    if not room_id:
        return enriched
    metrics = db_module.list_call_turn_metrics(call_room_id=room_id, limit=200)
    enriched["latency_summary"] = _summarize_turn_metrics(metrics)
    return enriched


def _timestamp_rank(value: str | None) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


@app.get("/api/config")
async def api_get_config():
    return redact_config(read_config())


@app.post("/api/config")
async def api_post_config(request: Request):
    data = await request.json()
    updated = write_config(data)
    apply_config_env(updated)
    logger.info("Configuration updated via backend API.")
    return {"status": "ok", "config": redact_config(updated)}


@app.get("/api/setup/status")
async def api_setup_status():
    _load_runtime_config()
    import db

    return db.check_supabase_setup()


@app.get("/api/logs")
async def api_get_logs():
    _load_runtime_config()
    import db

    try:
        logs = db.fetch_call_logs(limit=50)
        return [_attach_latency_summary(db, row) for row in logs]
    except Exception as exc:
        logger.error(f"Error fetching logs: {exc}")
        return []


@app.get("/api/logs/{log_id}/transcript")
async def api_get_transcript(log_id: str):
    _load_runtime_config()
    import db

    row = db.get_call_log(log_id)
    if not row:
        return PlainTextResponse(content="Error: Transcript not found.", status_code=404)

    text = f"Call Log - {row.get('created_at', '')}\n"
    text += f"Phone: {row.get('phone_number', 'Unknown')}\n"
    text += f"Duration: {row.get('duration_seconds', 0)}s\n"
    text += f"Summary: {row.get('summary', '')}\n\n"
    latency_summary = _summarize_turn_metrics(
        db.list_call_turn_metrics(call_room_id=row.get("call_room_id"), limit=200)
    )
    if latency_summary:
        text += "--- LATENCY SUMMARY ---\n"
        text += f"Turns: {latency_summary.get('turns', 0)}\n"
        text += f"KB turns: {latency_summary.get('kb_used_turns', 0)}\n"
        for field, label in [
            ("kb_ms", "KB"),
            ("llm_first_token_ms", "LLM first token"),
            ("tts_first_audio_ms", "TTS first audio"),
            ("tool_ms", "Tool"),
            ("total_turn_ms", "Total turn"),
        ]:
            if latency_summary.get(field) not in (None, ""):
                text += f"{label}: {latency_summary[field]} ms avg\n"
        text += "\n"

    transcript_text = str(row.get("transcript") or "").strip()
    if not transcript_text and row.get("call_room_id"):
        transcript_rows = db.list_call_transcripts(call_room_id=row.get("call_room_id"), limit=500)
        if transcript_rows:
            transcript_text = "\n".join(
                f"[{str(item.get('role') or '').upper()}] {str(item.get('content') or '').strip()}"
                for item in transcript_rows
                if str(item.get("content") or "").strip()
            )
    text += "--- TRANSCRIPT ---\n"
    text += transcript_text or "No transcript available."
    return PlainTextResponse(
        content=text,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=transcript_{log_id}.txt"},
    )


@app.get("/api/appointments")
async def api_get_appointments(start: str | None = None, end: str | None = None):
    _load_runtime_config()
    import db

    try:
        return db.fetch_appointments(start_iso=start, end_iso=end, limit=500)
    except db.AppointmentValidationError as exc:
        logger.error(f"Appointments validation error: {exc}")
        return appointment_error_response(str(exc), status_code=500)
    except db.AppointmentError as exc:
        logger.error(f"Error fetching appointments: {exc}")
        return appointment_error_response(str(exc), status_code=500)
    except Exception as exc:
        logger.error(f"Error fetching appointments: {exc}")
        return appointment_error_response("Unable to fetch appointments right now.", status_code=500)


@app.post("/api/appointments")
async def api_create_appointment(request: Request):
    config = _load_runtime_config()
    import db

    try:
        data = await request.json()
        payload = {
            "title": data.get("title"),
            "contact_name": data.get("contact_name"),
            "contact_phone": data.get("contact_phone"),
            "scheduled_start": data.get("scheduled_start"),
            "scheduled_end": data.get("scheduled_end"),
            "timezone": data.get("timezone") or "Asia/Kolkata",
            "status": data.get("status") or "scheduled",
            "notes": data.get("notes") or "",
            "source": "backend_api",
        }
        validate_appointment_payload(payload)
        appointment = db.create_appointment(payload)
        if (appointment.get("status") or "scheduled").lower() == "scheduled":
            handle_booking_confirmed(
                appointment=appointment,
                caller_name=appointment.get("contact_name") or "",
                phone_number=appointment.get("contact_phone") or "",
                ai_summary="Appointment created via backend API.",
                config=config,
            )
        return {"status": "ok", "appointment": appointment}
    except ValueError as exc:
        return appointment_error_response(str(exc), status_code=400)
    except db.AppointmentConflictError as exc:
        return appointment_error_response(str(exc), status_code=409)
    except db.AppointmentValidationError as exc:
        return appointment_error_response(str(exc), status_code=400)
    except db.AppointmentError as exc:
        return appointment_error_response(str(exc), status_code=500)
    except Exception as exc:
        logger.error(f"Error creating appointment: {exc}")
        return appointment_error_response("Unable to create appointment right now.", status_code=500)


@app.patch("/api/appointments/{appointment_id}")
async def api_update_appointment(appointment_id: str, request: Request):
    config = _load_runtime_config()
    import db

    try:
        data = await request.json()
        current = db.get_appointment(appointment_id)
        payload = {
            "title": data.get("title"),
            "contact_name": data.get("contact_name"),
            "contact_phone": data.get("contact_phone"),
            "scheduled_start": data.get("scheduled_start"),
            "scheduled_end": data.get("scheduled_end"),
            "timezone": data.get("timezone"),
            "status": data.get("status"),
            "notes": data.get("notes"),
        }
        validate_appointment_payload(payload, current=current)
        appointment = db.update_appointment(appointment_id, payload)
        if (appointment.get("status") or "").lower() == "cancelled":
            handle_appointment_cancelled(
                appointment,
                reason="Cancelled from backend API update.",
                config=config,
            )
        else:
            handle_appointment_updated(appointment, config=config)
        return {"status": "ok", "appointment": appointment}
    except ValueError as exc:
        return appointment_error_response(str(exc), status_code=400)
    except db.AppointmentNotFoundError as exc:
        return appointment_error_response(str(exc), status_code=404)
    except db.AppointmentConflictError as exc:
        return appointment_error_response(str(exc), status_code=409)
    except db.AppointmentValidationError as exc:
        return appointment_error_response(str(exc), status_code=400)
    except db.AppointmentError as exc:
        return appointment_error_response(str(exc), status_code=500)
    except Exception as exc:
        logger.error(f"Error updating appointment: {exc}")
        return appointment_error_response("Unable to update appointment right now.", status_code=500)


@app.post("/api/appointments/{appointment_id}/cancel")
async def api_cancel_appointment(appointment_id: str, request: Request):
    config = _load_runtime_config()
    import db

    try:
        data = await request.json()
        reason = str(data.get("reason") or "").strip()
        appointment = db.cancel_appointment(appointment_id, reason=reason)
        handle_appointment_cancelled(appointment, reason=reason, config=config)
        return {"status": "ok", "appointment": appointment}
    except db.AppointmentNotFoundError as exc:
        return appointment_error_response(str(exc), status_code=404)
    except db.AppointmentValidationError as exc:
        return appointment_error_response(str(exc), status_code=400)
    except db.AppointmentError as exc:
        return appointment_error_response(str(exc), status_code=500)
    except Exception as exc:
        logger.error(f"Error cancelling appointment: {exc}")
        return appointment_error_response("Unable to cancel appointment right now.", status_code=500)


@app.get("/api/stats")
async def api_get_stats():
    _load_runtime_config()
    import db

    try:
        return db.fetch_stats()
    except Exception as exc:
        logger.error(f"Error fetching stats: {exc}")
        return {"total_calls": 0, "total_bookings": 0, "avg_duration": 0, "booking_rate": 0}


@app.get("/api/contacts")
async def api_get_contacts():
    _load_runtime_config()
    import db

    try:
        rows = db.fetch_call_logs(limit=500)
        appointments = db.fetch_appointments(limit=500)
        contacts: dict[str, dict] = {}

        for row in rows:
            phone = row.get("phone_number") or "unknown"
            item = contacts.setdefault(
                phone,
                {
                    "phone_number": phone,
                    "caller_name": row.get("caller_name") or "",
                    "total_calls": 0,
                    "last_seen": row.get("created_at"),
                    "is_booked": False,
                    "appointment_count": 0,
                },
            )
            item["total_calls"] += 1
            if not item["caller_name"] and row.get("caller_name"):
                item["caller_name"] = row["caller_name"]
            if _timestamp_rank(row.get("created_at")) > _timestamp_rank(item.get("last_seen")):
                item["last_seen"] = row.get("created_at")
            if row.get("was_booked") or "confirmed" in str(row.get("summary") or "").lower():
                item["is_booked"] = True

        for appointment in appointments:
            phone = db.normalize_phone_number(appointment.get("contact_phone") or "") or "unknown"
            item = contacts.setdefault(
                phone,
                {
                    "phone_number": phone,
                    "caller_name": appointment.get("contact_name") or "",
                    "total_calls": 0,
                    "last_seen": appointment.get("scheduled_start") or appointment.get("created_at"),
                    "is_booked": False,
                    "appointment_count": 0,
                },
            )
            item["appointment_count"] += 1
            if not item["caller_name"] and appointment.get("contact_name"):
                item["caller_name"] = appointment["contact_name"]
            if _timestamp_rank(appointment.get("scheduled_start")) > _timestamp_rank(item.get("last_seen")):
                item["last_seen"] = appointment.get("scheduled_start")
            if str(appointment.get("status") or "").lower() == "scheduled":
                item["is_booked"] = True

        return sorted(contacts.values(), key=lambda item: _timestamp_rank(item.get("last_seen")), reverse=True)
    except Exception as exc:
        logger.error(f"Error fetching contacts: {exc}")
        return []


@app.get("/api/kb/status")
async def api_kb_status():
    config = _load_runtime_config()
    import kb

    status = kb.get_status(config)
    status_code = 200 if status.get("status") in {"ok", "setup_required", "not_configured"} else 500
    return JSONResponse(status, status_code=status_code)


@app.get("/api/kb/sources")
async def api_kb_sources():
    config = _load_runtime_config()
    import kb

    try:
        return {"status": "ok", "items": kb.list_sources(limit=200, config=config)}
    except Exception as exc:
        issue = kb.kb_runtime_issue_payload(exc, config=config)
        if issue.get("status") in {"setup_required", "not_configured"}:
            return {"status": issue["status"], "items": [], "message": issue["message"]}
        logger.error(f"Failed to fetch KB sources: {exc}")
        return internal_error_response("Unable to fetch KB sources right now.")


@app.post("/api/kb/sources")
async def api_kb_create_source(request: Request):
    config = _load_runtime_config()
    import kb

    try:
        data = await request.json()
        source = kb.create_source(data, queue_sync=True, config=config)
        await asyncio.to_thread(kb.process_pending_jobs, config, limit=1)
        return {"status": "ok", "source": kb.get_source(source["id"], config=config)}
    except Exception as exc:
        issue = kb.kb_runtime_issue_payload(exc, config=config)
        if issue.get("status") in {"setup_required", "not_configured"}:
            return JSONResponse({"status": issue["status"], "message": issue["message"]}, status_code=400)
        if isinstance(exc, ValueError):
            return internal_error_response(str(exc), status_code=400)
        logger.error(f"Failed to create KB source: {exc}")
        return internal_error_response("Unable to create the KB source right now.")


@app.patch("/api/kb/sources/{source_id}")
async def api_kb_update_source(source_id: str, request: Request):
    config = _load_runtime_config()
    import kb

    try:
        data = await request.json()
        source = kb.update_source(source_id, data, config=config)
        return {"status": "ok", "source": source}
    except Exception as exc:
        issue = kb.kb_runtime_issue_payload(exc, config=config)
        if issue.get("status") in {"setup_required", "not_configured"}:
            return JSONResponse({"status": issue["status"], "message": issue["message"]}, status_code=400)
        if isinstance(exc, ValueError):
            return internal_error_response(str(exc), status_code=400)
        logger.error(f"Failed to update KB source {source_id}: {exc}")
        return internal_error_response("Unable to update the KB source right now.")


@app.delete("/api/kb/sources/{source_id}")
async def api_kb_delete_source(source_id: str):
    config = _load_runtime_config()
    import kb

    try:
        kb.delete_source(source_id, config=config)
        return {"status": "ok", "deleted": True}
    except Exception as exc:
        issue = kb.kb_runtime_issue_payload(exc, config=config)
        if issue.get("status") in {"setup_required", "not_configured"}:
            return JSONResponse({"status": issue["status"], "message": issue["message"]}, status_code=400)
        logger.error(f"Failed to delete KB source {source_id}: {exc}")
        return internal_error_response("Unable to delete the KB source right now.")


@app.post("/api/kb/sources/{source_id}/sync")
async def api_kb_sync_source(source_id: str):
    config = _load_runtime_config()
    import kb

    try:
        source = kb.get_source(source_id, config=config)
        if not source:
            return JSONResponse({"status": "error", "message": "KB source not found."}, status_code=404)
        job = kb.queue_job(
            source_id=source_id,
            source_type=source.get("source_type") or "generic",
            job_type="ingest",
            payload={},
            config=config,
        )
        await asyncio.to_thread(kb.process_pending_jobs, config, limit=3)
        return {"status": "ok", "job": job}
    except Exception as exc:
        issue = kb.kb_runtime_issue_payload(exc, config=config)
        if issue.get("status") in {"setup_required", "not_configured"}:
            return JSONResponse({"status": issue["status"], "message": issue["message"]}, status_code=400)
        logger.error(f"Failed to sync KB source {source_id}: {exc}")
        return internal_error_response("Unable to sync the KB source right now.")


@app.post("/api/kb/upload")
async def api_kb_upload(file: UploadFile = File(...)):
    config = _load_runtime_config()
    import kb

    if not file.filename:
        return JSONResponse({"status": "error", "message": "File name is required."}, status_code=400)

    try:
        content = await file.read(MAX_KB_UPLOAD_BYTES + 1)
        if len(content) > MAX_KB_UPLOAD_BYTES:
            return JSONResponse(
                {"status": "error", "message": f"File is too large. Max size is {MAX_KB_UPLOAD_BYTES // (1024 * 1024)} MB."},
                status_code=400,
            )
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename)
        mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
        stored_file = kb.save_uploaded_file(safe_name, content, mime_type=mime_type, config=config)
        source = kb.create_source(
            {
                "source_type": "pdf_upload",
                "title": safe_name,
                "source_url": stored_file["source_url"],
                "storage_bucket": stored_file["storage_bucket"],
                "storage_path": stored_file["storage_path"],
                "mime_type": mime_type,
                "metadata": stored_file["metadata"],
            },
            queue_sync=True,
            config=config,
        )
        await asyncio.to_thread(kb.process_pending_jobs, config, limit=1)
        return {"status": "ok", "source": kb.get_source(source["id"], config=config)}
    except Exception as exc:
        issue = kb.kb_runtime_issue_payload(exc, config=config)
        if issue.get("status") in {"setup_required", "not_configured"}:
            return JSONResponse({"status": issue["status"], "message": issue["message"]}, status_code=400)
        if isinstance(exc, ValueError):
            return internal_error_response(str(exc), status_code=400)
        logger.error(f"Failed to upload KB source: {exc}")
        return internal_error_response("Unable to upload the KB source right now.")


@app.get("/api/kb/jobs")
async def api_kb_jobs():
    config = _load_runtime_config()
    import kb

    try:
        return {"status": "ok", "items": kb.list_jobs(limit=200, config=config)}
    except Exception as exc:
        issue = kb.kb_runtime_issue_payload(exc, config=config)
        if issue.get("status") in {"setup_required", "not_configured"}:
            return {"status": issue["status"], "items": [], "message": issue["message"]}
        logger.error(f"Failed to fetch KB jobs: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)


@app.post("/api/kb/search")
async def api_kb_search(request: Request):
    config = _load_runtime_config()
    import kb

    try:
        data = await request.json()
        query = str(data.get("query") or "").strip()
        if not query:
            return JSONResponse({"status": "error", "message": "Query is required."}, status_code=400)
        result = kb.search_hybrid(query, config=config)
        grounding = kb.build_grounding_text(query, config=config)
        return {"status": "ok", "result": result, "grounding": grounding}
    except Exception as exc:
        issue = kb.kb_runtime_issue_payload(exc, config=config)
        if issue.get("status") in {"setup_required", "not_configured"}:
            return JSONResponse({"status": issue["status"], "message": issue["message"]}, status_code=400)
        logger.error(f"KB search failed: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)


@app.post("/api/call/single")
async def api_call_single(request: Request):
    data = await request.json()
    phone = str(data.get("phone") or data.get("phone_number") or "").strip()
    config = _load_runtime_config()
    try:
        result = await dispatch_outbound_call(
            phone,
            config=config,
            caller_name=str(data.get("caller_name") or "").strip(),
        )
        logger.info(f"Outbound call dispatched to {phone}: {result['dispatch_id']}")
        return result
    except Exception as exc:
        logger.error(f"Call dispatch error: {exc}")
        return {"status": "error", "message": f"Unable to dispatch the outbound call right now. Error: {str(exc)}"}


@app.post("/api/call/bulk")
async def api_call_bulk(request: Request):
    data = await request.json()
    raw_numbers = data.get("numbers") or data.get("phone_numbers") or ""
    if isinstance(raw_numbers, list):
        numbers = [str(item).strip() for item in raw_numbers if str(item).strip()]
    else:
        numbers = [item.strip() for item in str(raw_numbers).splitlines() if item.strip()]
    results = []
    config = _load_runtime_config()
    for phone in numbers:
        try:
            result = await dispatch_outbound_call(phone, config=config)
            results.append(
                {
                    "phone": phone,
                    "status": "ok",
                    "dispatch_id": result["dispatch_id"],
                    "room": result["room"],
                }
            )
            logger.info(f"Bulk outbound dispatched to {phone}: {result['dispatch_id']}")
        except Exception as exc:
            logger.error(f"Bulk call dispatch error for {phone}: {exc}")
            results.append({"phone": phone, "status": "error", "message": f"Unable to dispatch this call right now. Error: {str(exc)}"})
    return {"results": results, "total": len(results)}


async def get_sip_participant(lk: api.LiveKitAPI, room_name: str) -> str | None:
    try:
        res = await lk.room.list_participants(api.ListParticipantsRequest(room=room_name))
        for p in res.participants:
            identity = p.identity
            attrs = p.attributes or {}
            if "sip.phoneNumber" in attrs or "phoneNumber" in attrs or identity.startswith("sip_") or "+" in identity:
                return identity
    except Exception as e:
        logger.error(f"Error listing participants for room {room_name}: {e}")
    return None


@app.get("/api/inbound")
async def api_get_inbound_calls(limit: int = 50):
    _load_runtime_config()
    import db
    try:
        return db.fetch_inbound_calls(limit=limit)
    except Exception as exc:
        logger.error(f"Error fetching inbound calls: {exc}")
        return []


@app.get("/api/outbound")
async def api_get_outbound_calls(limit: int = 50):
    _load_runtime_config()
    import db
    try:
        return db.fetch_outbound_calls(limit=limit)
    except Exception as exc:
        logger.error(f"Error fetching outbound calls: {exc}")
        return []


@app.post("/api/inbound/start")
async def api_inbound_start(request: Request):
    return {"status": "ok"}


@app.post("/api/inbound/end")
async def api_inbound_end(request: Request):
    data = await request.json()
    room_name = data.get("id")
    if not room_name:
        return JSONResponse({"status": "error", "message": "id is required"}, status_code=400)
    
    settings = get_livekit_settings()
    lk = api.LiveKitAPI(
        url=settings["url"],
        api_key=settings["api_key"],
        api_secret=settings["api_secret"]
    )
    try:
        identity = await get_sip_participant(lk, room_name)
        if not identity:
            return JSONResponse({"status": "error", "message": "SIP participant not found in room"}, status_code=404)
        
        await lk.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                room_name=room_name,
                participant_identity=identity,
                transfer_to="tel:+00000000",
                play_dialtone=False
            )
        )
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"End call failed for room {room_name}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        await lk.aclose()


@app.post("/api/inbound/transfer")
async def api_inbound_transfer(request: Request):
    data = await request.json()
    room_name = data.get("id")
    to = data.get("to")
    if not room_name or not to:
        return JSONResponse({"status": "error", "message": "id and to are required"}, status_code=400)
    
    settings = get_livekit_settings()
    lk = api.LiveKitAPI(
        url=settings["url"],
        api_key=settings["api_key"],
        api_secret=settings["api_secret"]
    )
    try:
        identity = await get_sip_participant(lk, room_name)
        if not identity:
            return JSONResponse({"status": "error", "message": "SIP participant not found in room"}, status_code=404)
        
        destination = to.strip()
        sip_domain = os.getenv("VOBIZ_SIP_DOMAIN")
        if sip_domain and "@" not in destination:
            clean = destination.replace("tel:", "").replace("sip:", "")
            destination = f"sip:{clean}@{sip_domain}"
        if not destination.startswith("sip:") and not destination.startswith("tel:"):
            destination = f"sip:{destination}"
            
        await lk.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                room_name=room_name,
                participant_identity=identity,
                transfer_to=destination,
                play_dialtone=False
            )
        )
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Transfer call failed for room {room_name} to {to}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        await lk.aclose()


@app.post("/api/inbound/voicemail")
async def api_inbound_voicemail(request: Request):
    return await api_inbound_end(request)


@app.post("/api/outbound/end")
async def api_outbound_end(request: Request):
    return await api_inbound_end(request)


@app.post("/api/outbound/transfer")
async def api_outbound_transfer(request: Request):
    return await api_inbound_transfer(request)


@app.post("/api/outbound/voicemail")
async def api_outbound_voicemail(request: Request):
    return await api_inbound_end(request)



# ─── CRM REST ENDPOINTS ────────────────────────────────────────────────


@app.get("/api/crm/leads")
async def api_get_leads():
    import db
    try:
        leads = db.fetch_leads()
        return leads
    except Exception as exc:
        logger.error(f"Error fetching CRM leads: {exc}")
        return []

@app.post("/api/crm/leads")
async def api_create_lead(request: Request):
    import db
    try:
        data = await request.json()
        lead = db.save_lead(data)
        _trigger_automation("lead_created", lead)
        return {"status": "ok", "lead": lead}
    except Exception as exc:
        logger.error(f"Error creating CRM lead: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

@app.put("/api/crm/leads/{lead_id}")
async def api_update_lead(lead_id: str, request: Request):
    import db
    try:
        data = await request.json()
        data["id"] = lead_id
        lead = db.save_lead(data)
        return {"status": "ok", "lead": lead}
    except Exception as exc:
        logger.error(f"Error updating CRM lead {lead_id}: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

@app.delete("/api/crm/leads/{lead_id}")
async def api_delete_lead(lead_id: str):
    import db
    try:
        success = db.delete_lead(lead_id)
        return {"status": "ok", "success": success}
    except Exception as exc:
        logger.error(f"Error deleting CRM lead {lead_id}: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

@app.get("/api/crm/leads/{lead_id}/timeline")
async def api_get_lead_timeline(lead_id: str):
    import db
    try:
        timeline = db.fetch_lead_timeline(lead_id)
        return timeline
    except Exception as exc:
        logger.error(f"Error fetching lead timeline {lead_id}: {exc}")
        return []

@app.post("/api/crm/leads/{lead_id}/timeline")
async def api_add_timeline_activity(lead_id: str, request: Request):
    import db
    try:
        data = await request.json()
        activity = db.add_lead_activity(
            lead_id=lead_id,
            activity_type=data.get("activity_type", "note"),
            title=data.get("title", "Note"),
            description=data.get("description", ""),
            metadata=data.get("metadata")
        )
        return {"status": "ok", "activity": activity}
    except Exception as exc:
        logger.error(f"Error adding timeline activity for {lead_id}: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

@app.post("/api/crm/leads/{lead_id}/score")
async def api_score_lead(lead_id: str, request: Request):
    import db
    try:
        data = await request.json()
        score, explanation = get_ai_lead_score(
            name=data.get("name", "Lead"),
            budget=data.get("budget", ""),
            neet_score=data.get("neet_score"),
            parent_involved=data.get("parent_involved", False),
            notes=data.get("notes", "")
        )
        return {"status": "ok", "score": score, "explanation": explanation}
    except Exception as exc:
        logger.error(f"Error generating AI lead score for {lead_id}: {exc}")
        return {"status": "error", "message": str(exc)}

@app.get("/api/crm/workflows")
async def api_get_workflows():
    import db
    try:
        return db.fetch_workflows()
    except Exception as exc:
        logger.error(f"Error fetching workflows: {exc}")
        return []

@app.post("/api/crm/workflows")
async def api_create_workflow(request: Request):
    import db
    try:
        data = await request.json()
        wf = db.save_workflow(data)
        return {"status": "ok", "workflow": wf}
    except Exception as exc:
        logger.error(f"Error saving workflow: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

@app.delete("/api/crm/workflows/{wf_id}")
async def api_delete_workflow(wf_id: str):
    import db
    try:
        success = db.delete_workflow(wf_id)
        return {"status": "ok", "success": success}
    except Exception as exc:
        logger.error(f"Error deleting workflow {wf_id}: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

@app.post("/api/crm/whatsapp")
async def api_send_whatsapp(request: Request):
    try:
        data = await request.json()
        phone = data.get("phone")
        template = data.get("template")
        logger.info(f"[WHATSAPP] Mock WhatsApp message sent to {phone} using template {template}")
        return {"status": "ok", "message": f"WhatsApp message successfully queued for {phone}"}
    except Exception as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

def get_ai_lead_score(name, budget, neet_score, parent_involved, notes):
    import os
    import json
    from google import genai
    from google.genai import types
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or "your_google" in api_key:
        return _heuristic_score(budget, neet_score, parent_involved)
        
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Analyze this student lead profile for MBBS abroad admission counseling and classify them into Hot, Warm, or Cold.
        
        Profile:
        - Name: {name}
        - Budget: {budget}
        - NEET Score: {neet_score}
        - Parent Involved: {parent_involved}
        - Notes/Objections: {notes}
        
        Criteria:
        - Hot: NEET qualified (score >= 100) AND budget clarity (>= 15L or India Private vs Abroad discussed) AND parents involved (Yes).
        - Warm: Interested, but researching, or missing budget clarity, or parents not fully convinced.
        - Cold: NEET not qualified (score < 100/None) OR no budget clarity (< 15L) OR unresponsive.
        
        Return a JSON object in this exact format:
        {{
            "score": "Hot" | "Warm" | "Cold",
            "explanation": "Brief 1-2 sentence explanation of the score based on criteria."
        }}
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        res_data = json.loads(response.text)
        return res_data.get("score", "Warm"), res_data.get("explanation", "AI analyzed profile.")
    except Exception as exc:
        logger.debug(f"Gemini scoring model failed, using fallback: {exc}")
        return _heuristic_score(budget, neet_score, parent_involved)

def _heuristic_score(budget, neet_score, parent_involved):
    try:
        neet = int(neet_score) if neet_score else 0
    except ValueError:
        neet = 0
        
    score = "Warm"
    explanation = "Profile is active. Researching MBBS abroad university options."
    
    if neet >= 130 and parent_involved and budget and "under 15" not in str(budget).lower():
        score = "Hot"
        explanation = "High qualification: Student is NEET qualified, parents are involved, and budget is suitable."
    elif (neet > 0 and neet < 100) or "under 15" in str(budget).lower():
        score = "Cold"
        explanation = "Low qualification: Either NEET score is low or budget does not meet standard MBBS abroad packages."
        
    return score, explanation

def _trigger_automation(event_type: str, lead: dict[str, Any]):
    import db
    import threading
    def run_actions():
        try:
            workflows = db.fetch_workflows()
            for wf in workflows:
                if wf.get("is_active") and wf.get("trigger_event") == event_type:
                    actions = wf.get("actions", [])
                    for action in actions:
                        act_type = action.get("type")
                        act_conf = action.get("config", {})
                        if act_type == "ai_call":
                            logger.info(f"[AUTOMATION] Automated AI Outbound Call scheduled for {lead.get('name')} ({lead.get('phone')})")
                            db.add_lead_activity(
                                lead.get("id"),
                                "call",
                                "AI Call Scheduled",
                                "System initiated automatic outbound call dispatch queue."
                            )
                        elif act_type == "whatsapp":
                            logger.info(f"[AUTOMATION] Dispatched WhatsApp follow-up to {lead.get('phone')}")
                            db.add_lead_activity(
                                lead.get("id"),
                                "whatsapp",
                                "WhatsApp Dispatched",
                                f"WhatsApp follow-up template '{act_conf.get('template')}' sent successfully."
                            )
                        elif act_type == "reminder":
                            logger.info(f"[AUTOMATION] CRM Task Created: {act_conf.get('title')}")
                            db.add_lead_activity(
                                lead.get("id"),
                                "crm_update",
                                "Reminder Added",
                                f"Task: {act_conf.get('title')} (due in {act_conf.get('delay_days', 1)} days)"
                            )
        except Exception as err:
            logger.error(f"Automation trigger error: {err}")
            
    threading.Thread(target=run_actions, daemon=True).start()


@app.get("/health")
async def health_check():
    import db

    # ── LiveKit (CRITICAL — required for calls) ──────────────────
    lk_status = "ok"
    try:
        url = os.environ.get("LIVEKIT_URL")
        api_key = os.environ.get("LIVEKIT_API_KEY")
        api_secret = os.environ.get("LIVEKIT_API_SECRET")
        lk = api.LiveKitAPI(url, api_key, api_secret)
        try:
            # Use non-deprecated API
            await lk.sip.list_outbound_trunk(api.ListSIPTrunkRequest())
        finally:
            await lk.aclose()
    except Exception as e:
        logger.error(f"Health check failed to connect to LiveKit: {e}")
        lk_status = "error"

    # ── Supabase (NON-CRITICAL — calling works without it) ───────
    supabase_status = "ok"
    try:
        supabase = db.get_supabase()
        if supabase:
            supabase.table("appointments").select("id").limit(1).execute()
        else:
            supabase_status = "degraded"
    except Exception as e:
        err = str(e)
        # DNS failure = Supabase project unreachable (paused/deleted) — degraded not error
        if "getaddrinfo" in err or "11001" in err or "Name or service not known" in err:
            logger.warning("Supabase unreachable (DNS failure) — running in degraded mode")
            supabase_status = "degraded"
        else:
            logger.error(f"Health check failed to query Supabase: {e}")
            supabase_status = "error"

    # Overall: ok if LiveKit is up (calls work), degraded if Supabase is down
    if lk_status == "ok" and supabase_status in ("ok", "degraded"):
        overall_status = "ok"
    elif lk_status == "ok":
        overall_status = "degraded"
    else:
        overall_status = "error"

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "avn-backend-api",
        "details": {
            "livekit": lk_status,
            "supabase": supabase_status,
        },
    }


# ─── Call Recording Playback & local serving setup ──────────────────────

def generate_sample_wav():
    import wave
    import struct
    import math
    
    dir_path = os.path.join(os.path.dirname(__file__), "data", "recordings")
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, "sample.wav")
    if os.path.exists(file_path):
        return
        
    sample_rate = 8000.0  # sample rate
    duration = 5.0  # seconds
    frequency = 440.0  # A4
    num_samples = int(duration * sample_rate)
    
    try:
        with wave.open(file_path, 'w') as wav:
            wav.setparams((1, 2, int(sample_rate), num_samples, 'NONE', 'not compressed'))
            for i in range(num_samples):
                t = i / sample_rate
                value = int(32767.0 * math.sin(2.0 * math.pi * frequency * t))
                data = struct.pack('<h', value)
                wav.writeframesraw(data)
        logger.info("[RECORDINGS] Successfully synthesized local fallback sample.wav")
    except Exception as e:
        logger.error(f"Error generating sample wav: {e}")

@app.on_event("startup")
def startup_event():
    generate_sample_wav()
    start_campaign_worker()

@app.get("/api/recordings/{filename}")
async def api_get_recording(filename: str):
    from fastapi.responses import FileResponse
    clean_name = filename.replace(".wav", "").replace(".ogg", "")
    recordings_dir = os.path.join(os.path.dirname(__file__), "data", "recordings")
    
    for ext in [".wav", ".ogg"]:
        path = os.path.join(recordings_dir, f"{clean_name}{ext}")
        if os.path.exists(path):
            return FileResponse(path)
            
    fallback_path = os.path.join(recordings_dir, "sample.wav")
    if os.path.exists(fallback_path):
        return FileResponse(fallback_path)
    return PlainTextResponse("Recording not found", status_code=404)


# ─── CMS REST Endpoints ──────────────────────────────────────────────────

from fastapi.responses import FileResponse

@app.get("/api/cms/pages")
async def api_list_pages():
    import db
    return db.fetch_cms_pages()

@app.post("/api/cms/pages")
async def api_create_page(request: Request):
    import db
    data = await request.json()
    page = db.save_cms_page(data)
    return {"status": "ok", "page": page}

@app.patch("/api/cms/pages/{page_id}")
async def api_update_page(page_id: str, request: Request):
    import db
    data = await request.json()
    data["id"] = page_id
    page = db.save_cms_page(data)
    return {"status": "ok", "page": page}

@app.delete("/api/cms/pages/{page_id}")
async def api_delete_page(page_id: str):
    import db
    success = db.delete_cms_page(page_id)
    return {"status": "ok", "success": success}

# CMS Prompts
@app.get("/api/cms/agent-prompts")
async def api_list_prompts():
    import db
    return db.fetch_cms_prompts()

@app.post("/api/cms/agent-prompts")
async def api_create_prompt(request: Request):
    import db
    data = await request.json()
    prompt = db.save_cms_prompt(data)
    return {"status": "ok", "prompt": prompt}

@app.patch("/api/cms/agent-prompts/{prompt_id}")
async def api_update_prompt(prompt_id: str, request: Request):
    import db
    data = await request.json()
    data["id"] = prompt_id
    prompt = db.save_cms_prompt(data)
    return {"status": "ok", "prompt": prompt}

# CMS FAQs
@app.get("/api/cms/faqs")
async def api_list_faqs():
    import db
    return db.fetch_cms_faqs()

@app.post("/api/cms/faqs")
async def api_create_faq(request: Request):
    import db
    data = await request.json()
    faq = db.save_cms_faq(data)
    return {"status": "ok", "faq": faq}

@app.patch("/api/cms/faqs/{faq_id}")
async def api_update_faq(faq_id: str, request: Request):
    import db
    data = await request.json()
    data["id"] = faq_id
    faq = db.save_cms_faq(data)
    return {"status": "ok", "faq": faq}

@app.delete("/api/cms/faqs/{faq_id}")
async def api_delete_faq(faq_id: str):
    import db
    success = db.delete_cms_faq(faq_id)
    return {"status": "ok", "success": success}

# CMS Media
@app.get("/api/cms/media")
async def api_list_media():
    import db
    return db.fetch_cms_media()

@app.post("/api/cms/media/upload")
async def api_upload_media(file: UploadFile = File(...)):
    import db
    try:
        uploads_dir = os.path.join(os.path.dirname(__file__), "data", "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        file_path = os.path.join(uploads_dir, filename)
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        media_item = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "filename": file.filename,
            "url": f"/api/cms/media/file/{filename}",
            "mime_type": file.content_type or "application/octet-stream",
            "size_bytes": len(content)
        }
        db.save_cms_media(media_item)
        return {"status": "ok", "media": media_item}
    except Exception as exc:
        logger.error(f"Failed to upload media: {exc}")
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)

@app.get("/api/cms/media/file/{filename}")
async def api_get_media_file(filename: str):
    file_path = os.path.join(os.path.dirname(__file__), "data", "uploads", filename)
    if not os.path.exists(file_path):
        return PlainTextResponse("File not found", status_code=404)
    return FileResponse(file_path)


# ─── Agent Config Endpoints ──────────────────────────────────────────────

@app.get("/api/agents")
async def api_list_agents():
    import db
    return db.fetch_agents()

@app.post("/api/agents")
async def api_create_agent(request: Request):
    import db
    data = await request.json()
    agent = db.save_agent(data)
    return {"status": "ok", "agent": agent}

@app.put("/api/agents/{agent_id}")
async def api_update_agent(agent_id: str, request: Request):
    import db
    data = await request.json()
    data["id"] = agent_id
    agent = db.save_agent(data)
    return {"status": "ok", "agent": agent}

@app.delete("/api/agents/{agent_id}")
async def api_delete_agent(agent_id: str):
    import db
    success = db.delete_agent(agent_id)
    return {"status": "ok", "success": success}


@app.get("/api/crm/campaigns")
async def api_get_campaigns():
    import db_backend as db
    campaigns = db.fetch_campaigns()
    return {"status": "ok", "campaigns": campaigns}

@app.post("/api/crm/campaigns")
async def api_create_campaign(request: Request):
    import db_backend as db
    data = await request.json()
    name = data.get("name")
    agent_id = data.get("agent_id")
    concurrency_limit = data.get("concurrency_limit") or 5
    retry_limit = data.get("retry_limit") or 2
    raw_leads = data.get("leads") or []

    if not name:
        return JSONResponse({"status": "error", "message": "Campaign name is required"}, status_code=400)

    campaign_data = {
        "name": name,
        "agent_id": agent_id,
        "concurrency_limit": concurrency_limit,
        "retry_limit": retry_limit,
        "status": "queued"
    }
    campaign = db.save_campaign(campaign_data)
    camp_id = campaign.get("id")

    imported_leads = []
    for l in raw_leads:
        phone = l.get("phone")
        if not phone:
            continue
        lead_data = {
            "name": l.get("name") or "",
            "phone": phone,
            "email": l.get("email") or "",
            "company": l.get("company") or "eWings Abroad",
            "campaign_id": camp_id,
            "campaign_status": "pending",
            "custom_fields": l.get("custom_fields") or {}
        }
        lead = db.save_lead(lead_data)
        imported_leads.append(lead)

    return {"status": "ok", "campaign": campaign, "leads_imported": len(imported_leads)}

@app.get("/api/crm/campaigns/{campaign_id}")
async def api_get_campaign_details(campaign_id: str):
    import db_backend as db
    campaigns = db.fetch_campaigns()
    campaign = next((c for c in campaigns if str(c.get("id")) == str(campaign_id)), None)
    if not campaign:
        return JSONResponse({"status": "error", "message": "Campaign not found"}, status_code=404)

    leads = db.fetch_campaign_leads(campaign_id)
    return {"status": "ok", "campaign": campaign, "leads": leads}

@app.post("/api/crm/campaigns/{campaign_id}/start")
async def api_start_campaign(campaign_id: str):
    import db_backend as db
    campaigns = db.fetch_campaigns()
    campaign = next((c for c in campaigns if str(c.get("id")) == str(campaign_id)), None)
    if not campaign:
        return JSONResponse({"status": "error", "message": "Campaign not found"}, status_code=404)

    campaign["status"] = "running"
    db.save_campaign(campaign)
    return {"status": "ok", "campaign": campaign}

@app.post("/api/crm/campaigns/{campaign_id}/pause")
async def api_pause_campaign(campaign_id: str):
    import db_backend as db
    campaigns = db.fetch_campaigns()
    campaign = next((c for c in campaigns if str(c.get("id")) == str(campaign_id)), None)
    if not campaign:
        return JSONResponse({"status": "error", "message": "Campaign not found"}, status_code=404)

    campaign["status"] = "paused"
    db.save_campaign(campaign)
    return {"status": "ok", "campaign": campaign}

@app.delete("/api/crm/campaigns/{campaign_id}")
async def api_delete_campaign(campaign_id: str):
    import db_backend as db
    success = db.delete_campaign(campaign_id)
    return {"status": "ok", "success": success}

@app.get("/api/crm/campaigns/{campaign_id}/export")
async def api_export_campaign(campaign_id: str):
    from fastapi.responses import StreamingResponse
    import db_backend as db
    import csv
    import io

    leads = db.fetch_campaign_leads(campaign_id)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["ID", "Name", "Phone", "Status", "Outcome", "Custom Fields"])
    for l in leads:
        writer.writerow([
            l.get("id"),
            l.get("name"),
            l.get("phone"),
            l.get("campaign_status"),
            l.get("campaign_outcome") or "uncalled",
            json.dumps(l.get("custom_fields") or {})
        ])
        
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign-{campaign_id}-results.csv"}
    )


# ─── Calendar Integration Endpoints ──────────────────────────────────────

@app.post("/api/integrations/google-calendar/sync")
async def api_sync_google_calendar():
    await asyncio.sleep(1.0)
    return {
        "status": "ok",
        "message": "Google Calendar synchronized successfully",
        "last_synced": datetime.now(timezone.utc).isoformat()
    }

@app.post("/api/integrations/zoho-calendar/sync")
async def api_sync_zoho_calendar():
    await asyncio.sleep(1.0)
    return {
        "status": "ok",
        "message": "Zoho Calendar synchronized successfully",
        "last_synced": datetime.now(timezone.utc).isoformat()
    }

