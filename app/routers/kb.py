import asyncio
import logging
import mimetypes
import re

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

import kb
from app.core.auth_deps import RoleChecker, get_current_user
from app.core.runtime_config import MAX_KB_UPLOAD_BYTES, load_runtime_config as _load_runtime_config
from app.models.user import User

logger = logging.getLogger("kb-api")
router = APIRouter(prefix="/api/kb", tags=["Knowledge Base"])

ALLOWED_UPLOAD_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}


def _process_soon(config: dict, limit: int) -> None:
    # The KB worker also polls; job claiming is atomic, so both never run the same job.
    asyncio.create_task(asyncio.to_thread(kb.process_pending_jobs, config, limit=limit))


def _bad_request(exc: Exception) -> JSONResponse:
    return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)


@router.get("/status")
def kb_status(current_user: User = Depends(get_current_user)):
    status = kb.get_status(_load_runtime_config(), tenant_id=current_user.tenant_id)
    return JSONResponse(status, status_code=200 if status.get("status") == "ok" else 500)


@router.get("/sources")
def kb_sources(current_user: User = Depends(get_current_user)):
    return {"status": "ok", "items": kb.list_sources(limit=200, config=_load_runtime_config(), tenant_id=current_user.tenant_id)}


@router.post("/sources")
async def kb_create_source(request: Request, current_user: User = Depends(get_current_user)):
    """Create a website/sitemap (`web_url`) or pasted text (`text`) source and queue ingestion."""
    config = _load_runtime_config()
    data = await request.json()
    try:
        source = kb.create_source(data, queue_sync=True, config=config, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        return _bad_request(exc)
    _process_soon(config, limit=1)
    return {"status": "ok", "source": source}


@router.patch("/sources/{source_id}")
async def kb_update_source(source_id: str, request: Request, current_user: User = Depends(get_current_user)):
    data = await request.json()
    config = _load_runtime_config()
    if not kb.get_source(source_id, config=config, tenant_id=current_user.tenant_id):
        raise HTTPException(status_code=404, detail="KB source not found")
    try:
        source = kb.update_source(source_id, data, config=config, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        return _bad_request(exc)
    return {"status": "ok", "source": source}


@router.delete("/sources/{source_id}")
def kb_delete_source(source_id: str, current_user: User = Depends(get_current_user)):
    if not kb.delete_source(source_id, config=_load_runtime_config(), tenant_id=current_user.tenant_id):
        raise HTTPException(status_code=404, detail="KB source not found")
    return {"status": "ok", "deleted": True}


@router.post("/sources/{source_id}/sync")
def kb_sync_source(source_id: str, current_user: User = Depends(get_current_user)):
    """Re-fetch and re-index a source."""
    config = _load_runtime_config()
    source = kb.get_source(source_id, config=config, tenant_id=current_user.tenant_id)
    if not source:
        raise HTTPException(status_code=404, detail="KB source not found")
    job = kb.queue_job(source_id=source["id"], source_type=source["source_type"], job_type="ingest",
                       config=config, tenant_id=current_user.tenant_id)
    _process_soon(config, limit=3)
    return {"status": "ok", "job": job}


@router.post("/reindex")
def kb_reindex(current_user: User = Depends(RoleChecker(["Manager"]))):
    """Re-embed chunks created with a different embedding model (e.g. after switching providers)."""
    config = _load_runtime_config()
    jobs = kb.reindex_stale_sources(config=config, tenant_id=current_user.tenant_id)
    if jobs:
        _process_soon(config, limit=len(jobs))
    return {"status": "ok", "queued": len(jobs), "jobs": jobs}


@router.post("/upload")
async def kb_upload(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Upload a PDF, TXT, or Markdown document and queue ingestion."""
    config = _load_runtime_config()
    if not file.filename:
        return _bad_request(ValueError("File name is required."))
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_UPLOAD_TYPES:
        return _bad_request(ValueError(f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_TYPES))}"))
    content = await file.read(MAX_KB_UPLOAD_BYTES + 1)
    if len(content) > MAX_KB_UPLOAD_BYTES:
        return _bad_request(ValueError(f"File too large. Max size {MAX_KB_UPLOAD_BYTES // (1024 * 1024)}MB"))
    if ext == ".pdf" and not content.startswith(b"%PDF"):
        return _bad_request(ValueError("This file is not a valid PDF."))
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename)
    mime_type = ALLOWED_UPLOAD_TYPES[ext] or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    stored = kb.save_uploaded_file(safe_name, content, mime_type=mime_type, config=config)
    try:
        source = kb.create_source({
            "source_type": "pdf_upload", "title": safe_name, "source_url": stored["source_url"],
            "storage_bucket": stored["storage_bucket"], "storage_path": stored["storage_path"],
            "mime_type": mime_type, "metadata": stored["metadata"],
        }, queue_sync=True, config=config, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        return _bad_request(exc)
    _process_soon(config, limit=1)
    return {"status": "ok", "source": source}


@router.get("/jobs")
def kb_jobs(current_user: User = Depends(get_current_user)):
    return {"status": "ok", "items": kb.list_jobs(limit=200, config=_load_runtime_config(), tenant_id=current_user.tenant_id)}


@router.post("/search")
async def kb_search(request: Request, current_user: User = Depends(get_current_user)):
    """Test retrieval: returns matches and the grounding text the voice agent would receive."""
    config = _load_runtime_config()
    data = await request.json()
    query = str(data.get("query") or "").strip()
    if not query:
        return _bad_request(ValueError("Query is required."))
    result = await asyncio.to_thread(kb.search_hybrid, query, config=config, tenant_id=current_user.tenant_id)
    grounding = await asyncio.to_thread(kb.build_grounding_text, query, config=config, tenant_id=current_user.tenant_id)
    return {"status": "ok", "result": result, "grounding": grounding}
