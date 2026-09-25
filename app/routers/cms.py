import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
import os

from app.core.database import get_db
from app.models.cms import CMSPage, CMSPrompt, CMSFaq, CMSMedia
from app.schemas.cms import (
    CMSPageOut, CMSPageCreate, CMSPageUpdate,
    CMSPromptOut, CMSPromptCreate, CMSPromptUpdate,
    CMSFaqOut, CMSFaqCreate, CMSFaqUpdate,
    CMSMediaOut
)
from app.core.auth_deps import get_current_user
from app.services import media_files
from app.models.user import User

router = APIRouter(prefix="/api/cms", tags=["Content Management"])

def _ensure_slug_free(db: Session, tenant_id: str, slug: str) -> None:
    if db.query(CMSPage).filter(CMSPage.tenant_id == tenant_id, CMSPage.slug == slug).first():
        raise HTTPException(status_code=409, detail=f"A page with the slug '{slug}' already exists.")


# --- Pages ---
@router.get("/pages", response_model=List[CMSPageOut])
def list_pages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List site pages details."""
    return db.query(CMSPage).filter(
        CMSPage.tenant_id == current_user.tenant_id
    ).order_by(CMSPage.updated_at.desc()).all()

@router.post("/pages", response_model=CMSPageOut, status_code=status.HTTP_201_CREATED)
def create_page(
    payload: CMSPageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new page instance."""
    _ensure_slug_free(db, current_user.tenant_id, payload.slug)
    page = CMSPage(**payload.model_dump())
    page.tenant_id = current_user.tenant_id
    db.add(page)
    db.commit()
    db.refresh(page)
    return page

@router.patch("/pages/{id}", response_model=CMSPageOut)
def update_page(
    id: str,
    payload: CMSPageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update page properties."""
    page = db.query(CMSPage).filter(
        CMSPage.id == id,
        CMSPage.tenant_id == current_user.tenant_id
    ).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
        
    update_data = payload.model_dump(exclude_unset=True)
    if update_data.get("slug") and update_data["slug"] != page.slug:
        _ensure_slug_free(db, current_user.tenant_id, update_data["slug"])
    for key, value in update_data.items():
        setattr(page, key, value)

    page.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(page)
    return page

@router.delete("/pages/{id}")
def delete_page(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a page."""
    page = db.query(CMSPage).filter(
        CMSPage.id == id,
        CMSPage.tenant_id == current_user.tenant_id
    ).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
        
    db.delete(page)
    db.commit()
    return {"status": "ok"}

# --- Prompts ---
@router.get("/agent-prompts", response_model=List[CMSPromptOut])
def list_prompts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve list of system instructs."""
    return db.query(CMSPrompt).filter(
        CMSPrompt.tenant_id == current_user.tenant_id
    ).order_by(CMSPrompt.updated_at.desc()).all()

@router.post("/agent-prompts", response_model=CMSPromptOut, status_code=status.HTTP_201_CREATED)
def create_prompt(
    payload: CMSPromptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new prompt setting."""
    prompt = CMSPrompt(**payload.model_dump())
    prompt.tenant_id = current_user.tenant_id
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt

@router.patch("/agent-prompts/{id}", response_model=CMSPromptOut)
def update_prompt(
    id: str,
    payload: CMSPromptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update properties of system instructions."""
    prompt = db.query(CMSPrompt).filter(
        CMSPrompt.id == id,
        CMSPrompt.tenant_id == current_user.tenant_id
    ).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prompt, key, value)
        
    prompt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(prompt)
    return prompt

@router.delete("/agent-prompts/{id}")
def delete_prompt(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a prompt setting."""
    prompt = db.query(CMSPrompt).filter(
        CMSPrompt.id == id,
        CMSPrompt.tenant_id == current_user.tenant_id
    ).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    db.delete(prompt)
    db.commit()
    return {"status": "ok"}

# --- FAQs ---
@router.get("/faqs", response_model=List[CMSFaqOut])
def list_faqs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List FAQ sheets."""
    return db.query(CMSFaq).filter(
        CMSFaq.tenant_id == current_user.tenant_id
    ).order_by(CMSFaq.order).all()

@router.post("/faqs", response_model=CMSFaqOut, status_code=status.HTTP_201_CREATED)
def create_faq(
    payload: CMSFaqCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new FAQ record."""
    faq = CMSFaq(**payload.model_dump())
    faq.tenant_id = current_user.tenant_id
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq

@router.patch("/faqs/{id}", response_model=CMSFaqOut)
def update_faq(
    id: str,
    payload: CMSFaqUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update FAQ property fields."""
    faq = db.query(CMSFaq).filter(
        CMSFaq.id == id,
        CMSFaq.tenant_id == current_user.tenant_id
    ).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ sheet not found")
        
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(faq, key, value)
        
    db.commit()
    db.refresh(faq)
    return faq

@router.delete("/faqs/{id}")
def delete_faq(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a FAQ record."""
    faq = db.query(CMSFaq).filter(
        CMSFaq.id == id,
        CMSFaq.tenant_id == current_user.tenant_id
    ).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
        
    db.delete(faq)
    db.commit()
    return {"status": "ok"}

# --- Media Uploads ---
@router.get("/media", response_model=List[CMSMediaOut])
def list_media(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List uploaded assets index."""
    return db.query(CMSMedia).filter(
        CMSMedia.tenant_id == current_user.tenant_id
    ).order_by(CMSMedia.created_at.desc()).all()

@router.post("/media/upload", response_model=CMSMediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload an image, audio file, or PDF. The type is taken from the file's content, not its name."""
    contents = await file.read(media_files.MAX_MEDIA_BYTES + 1)
    if len(contents) > media_files.MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max size {media_files.MAX_MEDIA_BYTES // (1024 * 1024)}MB")
    ext = media_files.detect_type(contents)
    if ext is None:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload PNG, JPG, GIF, WebP, PDF, MP3, WAV, OGG or M4A.")

    # Generated name in a per-tenant folder: the client filename is untrusted.
    original_name = os.path.basename(file.filename or "upload")[:200]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    tenant_dir = media_files.MEDIA_ROOT / str(current_user.tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / stored_name).write_bytes(contents)

    media = CMSMedia(
        filename=original_name,
        url=f"/data/media/{current_user.tenant_id}/{stored_name}",
        mime_type=media_files.ALLOWED_TYPES[ext],
        size_bytes=len(contents),
        tenant_id=current_user.tenant_id
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


@router.delete("/media/{id}")
def delete_media(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    media = db.query(CMSMedia).filter(CMSMedia.id == id, CMSMedia.tenant_id == current_user.tenant_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    name = media.url.rsplit("/", 1)[-1]
    path = media_files.resolve(str(current_user.tenant_id), name)
    if path is not None:
        path.unlink(missing_ok=True)
    db.delete(media)
    db.commit()
    return {"status": "ok", "success": True}
