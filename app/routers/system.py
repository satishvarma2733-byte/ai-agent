"""Runtime configuration, call recordings, and third-party integration endpoints."""
import os
from datetime import timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.core.auth_deps import RoleChecker, get_current_user, oauth2_scheme
from app.core.database import get_db
from app.core.tenancy import bind_session_to_tenant
from app.services import audit, signed_urls
from config_crypto import SecretsKeyError
from app.core.runtime_config import load_runtime_config, public_config, update_config
from app.models.call import CallLog
from app.models.user import User

router = APIRouter(tags=["System"])

RECORDINGS_DIR = Path(os.getenv("APP_DATA_DIR", "data")) / "recordings"


@router.get("/api/system/status")
def system_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """What the status pill shows. `ready` means calls can work: database up and LiveKit and the model key configured.
    The voice worker runs separately and has no heartbeat, so only its last recorded call is reported."""
    try:
        db.execute(text("SELECT 1"))
        database = True
    except Exception:
        database = False
    from outbound_calls import get_livekit_settings
    config = load_runtime_config()
    livekit = get_livekit_settings(config)
    livekit_configured = bool(livekit["url"] and livekit["api_key"] and livekit["api_secret"])
    model_key_configured = bool(str(config.get("google_api_key") or os.getenv("GOOGLE_API_KEY", "")).strip())
    last_call_at = db.query(func.max(CallLog.created_at)).filter(CallLog.tenant_id == current_user.tenant_id).scalar()
    missing = [name for name, ok in (("database", database), ("LiveKit", livekit_configured), ("AI model key", model_key_configured)) if not ok]
    return {
        "ready": not missing,
        "missing": missing,
        "database": database,
        "livekit_configured": livekit_configured,
        "model_key_configured": model_key_configured,
        "last_call_at": last_call_at.replace(tzinfo=timezone.utc).isoformat() if last_call_at else None,
    }


@router.get("/api/config")
def get_config(current_user: User = Depends(RoleChecker(["Admin"]))):
    """Runtime voice configuration. Credentials are masked."""
    return public_config()


@router.post("/api/config")
async def post_config(
    request: Request,
    current_user: User = Depends(RoleChecker(["Admin"])),
    db: Session = Depends(get_db),
):
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Config payload must be a JSON object")
    try:
        update_config(data)
    except SecretsKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Key names only: values can be credentials.
    audit.record(db, action="config_updated", entity="RuntimeConfig", tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"keys": sorted(data.keys())}, request=request)
    return {"status": "ok", "config": public_config()}


@router.get("/api/recordings/{filename}")
def get_recording(
    filename: str,
    request: Request,
    t: str | None = None,
    exp: int | None = None,
    sig: str | None = None,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Serve a locally stored recording that belongs to one of the workspace's own calls, either to a signed-in
    member or through the signed link that call logs carry (audio players can't send the access token).
    Recordings in the private storage bucket are redirected to a one-minute signed storage URL."""
    name = Path(filename).name
    if t and exp is not None and sig and signed_urls.verify_recording_link(t, name, exp, sig):
        tenant_id = t
        bind_session_to_tenant(db, tenant_id)
    else:
        tenant_id = get_current_user(request, db, token).tenant_id
    stem = Path(name).stem
    owned = db.query(CallLog).filter(
        CallLog.tenant_id == tenant_id,
        or_(CallLog.call_room_id == stem, CallLog.recording_url.like(f"%/{name}")),
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    for ext in (".wav", ".ogg"):
        path = RECORDINGS_DIR / f"{stem}{ext}"
        if path.is_file():
            return FileResponse(path, headers={"Cache-Control": "private, no-store"})
    object_path = signed_urls.storage_object_path(owned.recording_url)
    if object_path:
        url = signed_urls.storage_download_url(object_path)
        if url:
            return RedirectResponse(url, status_code=302, headers={"Cache-Control": "private, no-store"})
    raise HTTPException(status_code=404, detail="Recording not found")

