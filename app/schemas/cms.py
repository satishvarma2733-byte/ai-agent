from pydantic import BaseModel
from typing import Optional, List
from app.schemas.common import UTCDateTime

# --- Pages ---
class CMSPageBase(BaseModel):
    title: str
    slug: str
    content: str
    status: str = "published"  # published | draft | archived
    category: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None

class CMSPageCreate(CMSPageBase):
    pass

class CMSPageUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None

class CMSPageOut(CMSPageBase):
    id: str
    created_at: UTCDateTime
    updated_at: UTCDateTime

    class Config:
        from_attributes = True

# --- Prompts ---
class CMSPromptBase(BaseModel):
    name: str
    content: str
    active: bool = True
    tags_csv: Optional[str] = None

class CMSPromptCreate(CMSPromptBase):
    pass

class CMSPromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    active: Optional[bool] = None
    tags_csv: Optional[str] = None

class CMSPromptOut(CMSPromptBase):
    id: str
    created_at: UTCDateTime
    updated_at: UTCDateTime

    class Config:
        from_attributes = True

# --- FAQs ---
class CMSFaqBase(BaseModel):
    question: str
    answer: str
    category: Optional[str] = None
    order: int = 0

class CMSFaqCreate(CMSFaqBase):
    pass

class CMSFaqUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    order: Optional[int] = None

class CMSFaqOut(CMSFaqBase):
    id: str

    class Config:
        from_attributes = True

# --- Media ---
class CMSMediaBase(BaseModel):
    filename: str
    url: str
    mime_type: str
    size_bytes: int

class CMSMediaCreate(CMSMediaBase):
    pass

class CMSMediaOut(CMSMediaBase):
    id: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True
