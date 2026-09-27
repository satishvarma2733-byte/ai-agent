"""Website chat widgets, API keys for the public chat API, and the public endpoints themselves."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.core.auth_deps import RoleChecker
from app.core.database import get_db
from app.core.security import hash_token
from app.core.settings import settings
from app.models.agent import Agent
from app.models.lead import Lead
from app.models.user import User
from app.models.widget import ApiKey, ChatSession, ChatWidget
from app.schemas.common import UTCDateTime
from app.schemas.lead import normalize_phone
from app.services import audit, public_chat

router = APIRouter(tags=["Website chat"])
public_router = APIRouter(tags=["Public chat API"])
require_admin = RoleChecker(["Admin"])
require_manager = RoleChecker(["Admin", "Manager"])

WIDGET_JS = Path(__file__).resolve().parent.parent / "public" / "widget.js"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _api_base(request: Request) -> str:
    return str(settings.public_api_url or request.base_url).rstrip("/")


# --- Admin: widgets ------------------------------------------------------------------------------

class WidgetIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    agent_id: str
    allowed_origins: List[str] = Field(min_length=1, max_length=public_chat.MAX_ORIGINS)
    greeting: Optional[str] = Field(default=None, max_length=500)
    color: str = "#7B61FF"
    voice_enabled: bool = False
    lead_capture: bool = True


class WidgetPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    agent_id: Optional[str] = None
    allowed_origins: Optional[List[str]] = Field(default=None, min_length=1, max_length=public_chat.MAX_ORIGINS)
    greeting: Optional[str] = Field(default=None, max_length=500)
    color: Optional[str] = None
    voice_enabled: Optional[bool] = None
    lead_capture: Optional[bool] = None
    enabled: Optional[bool] = None


class WidgetOut(BaseModel):
    id: str
    name: str
    agent_id: str
    agent_name: str
    agent_live: bool
    public_key: str
    allowed_origins: List[str]
    greeting: Optional[str] = None
    color: str
    voice_enabled: bool
    lead_capture: bool
    enabled: bool
    embed_code: str
    created_at: UTCDateTime


def _widget_out(db: Session, w: ChatWidget, request: Request) -> WidgetOut:
    agent = db.get(Agent, w.agent_id)
    snippet = f'<script src="{_api_base(request)}/widget.js" data-key="{w.public_key}" async></script>'
    return WidgetOut(id=w.id, name=w.name, agent_id=w.agent_id, agent_name=agent.name if agent else "(deleted)",
                     agent_live=bool(agent and agent.production_version_id and agent.disabled_at is None),
                     public_key=w.public_key, allowed_origins=list(w.allowed_origins or []), greeting=w.greeting,
                     color=w.color, voice_enabled=w.voice_enabled, lead_capture=w.lead_capture, enabled=w.enabled,
                     embed_code=snippet, created_at=w.created_at)


def _check(fn, *args):
    try:
        return fn(*args)
    except public_chat.PublicChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


def _tenant_agent(db: Session, agent_id: str, tenant_id: str) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.tenant_id == tenant_id).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _get_widget(db: Session, widget_id: str, tenant_id: str) -> ChatWidget:
    w = db.query(ChatWidget).filter(ChatWidget.id == widget_id, ChatWidget.tenant_id == tenant_id).first()
    if w is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    return w


@router.get("/api/widgets", response_model=List[WidgetOut])
def list_widgets(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = db.query(ChatWidget).filter(ChatWidget.tenant_id == current_user.tenant_id).order_by(ChatWidget.created_at).all()
    return [_widget_out(db, w, request) for w in rows]


@router.post("/api/widgets", response_model=WidgetOut, status_code=status.HTTP_201_CREATED)
def create_widget(payload: WidgetIn, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    _tenant_agent(db, payload.agent_id, current_user.tenant_id)
    w = ChatWidget(tenant_id=current_user.tenant_id, agent_id=payload.agent_id, name=payload.name.strip(),
                   public_key=public_chat.new_widget_key(),
                   allowed_origins=_check(public_chat.normalize_origins, payload.allowed_origins),
                   greeting=(payload.greeting or "").strip() or None, color=_check(public_chat.check_color, payload.color),
                   voice_enabled=payload.voice_enabled, lead_capture=payload.lead_capture, enabled=True,
                   created_by=current_user.id, created_at=_now(), updated_at=_now())
    db.add(w)
    db.commit()
    audit.record(db, action="widget_created", entity="ChatWidget", entity_id=w.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return _widget_out(db, w, request)


@router.patch("/api/widgets/{widget_id}", response_model=WidgetOut)
def update_widget(widget_id: str, payload: WidgetPatch, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    w = _get_widget(db, widget_id, current_user.tenant_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("agent_id"):
        _tenant_agent(db, data["agent_id"], current_user.tenant_id)
        w.agent_id = data["agent_id"]
    if data.get("allowed_origins") is not None:
        w.allowed_origins = _check(public_chat.normalize_origins, data["allowed_origins"])
    if data.get("color") is not None:
        w.color = _check(public_chat.check_color, data["color"])
    if data.get("name"):
        w.name = data["name"].strip()
    if "greeting" in data:
        w.greeting = (data["greeting"] or "").strip() or None
    for field in ("voice_enabled", "lead_capture", "enabled"):
        if data.get(field) is not None:
            setattr(w, field, data[field])
    w.updated_at = _now()
    db.commit()
    audit.record(db, action="widget_updated", entity="ChatWidget", entity_id=w.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return _widget_out(db, w, request)


@router.post("/api/widgets/{widget_id}/rotate-key", response_model=WidgetOut)
def rotate_widget_key(widget_id: str, request: Request, db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    """A new public key; the old embed code stops working."""
    w = _get_widget(db, widget_id, current_user.tenant_id)
    w.public_key = public_chat.new_widget_key()
    w.updated_at = _now()
    db.commit()
    audit.record(db, action="widget_key_rotated", entity="ChatWidget", entity_id=w.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return _widget_out(db, w, request)


@router.delete("/api/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_widget(widget_id: str, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    w = _get_widget(db, widget_id, current_user.tenant_id)
    db.delete(w)
    db.commit()
    audit.record(db, action="widget_deleted", entity="ChatWidget", entity_id=widget_id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Admin: API keys -----------------------------------------------------------------------------

class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: UTCDateTime
    last_used_at: Optional[UTCDateTime] = None
    revoked_at: Optional[UTCDateTime] = None


class ApiKeyCreatedOut(ApiKeyOut):
    key: str


def _key_out(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": k.created_at, "last_used_at": k.last_used_at,
            "revoked_at": k.revoked_at}


@router.get("/api/api-keys", response_model=List[ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = db.query(ApiKey).filter(ApiKey.tenant_id == current_user.tenant_id).order_by(ApiKey.created_at.desc()).all()
    return [ApiKeyOut(**_key_out(k)) for k in rows]


@router.post("/api/api-keys", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
def create_api_key(payload: ApiKeyIn, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    """The key is shown only in this response."""
    key = public_chat.new_api_key()
    row = ApiKey(tenant_id=current_user.tenant_id, name=payload.name.strip(), prefix=key[:12], key_hash=hash_token(key),
                 created_by=current_user.id, created_at=_now())
    db.add(row)
    db.commit()
    audit.record(db, action="api_key_created", entity="ApiKey", entity_id=row.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, request=request)
    return ApiKeyCreatedOut(**_key_out(row), key=key)


@router.delete("/api/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: str, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    row = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.tenant_id == current_user.tenant_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if row.revoked_at is None:
        row.revoked_at = _now()
        db.commit()
        audit.record(db, action="api_key_revoked", entity="ApiKey", entity_id=row.id, tenant_id=current_user.tenant_id,
                     user_id=current_user.id, request=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Conversations -------------------------------------------------------------------------------

class ChatTurnOut(BaseModel):
    role: str
    text: str


class ChatSessionOut(BaseModel):
    id: str
    source: str
    agent_name: str
    origin: Optional[str] = None
    lead_id: Optional[str] = None
    lead_name: Optional[str] = None
    messages: int
    turns: List[ChatTurnOut]
    created_at: UTCDateTime
    updated_at: UTCDateTime


@router.get("/api/chat-sessions", response_model=List[ChatSessionOut])
def list_chat_sessions(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_manager)):
    """The most recent website and API conversations."""
    rows = (db.query(ChatSession).filter(ChatSession.tenant_id == current_user.tenant_id)
            .order_by(ChatSession.updated_at.desc()).limit(max(1, min(limit, 200))).all())
    agents = {a.id: a.name for a in db.query(Agent).filter(Agent.id.in_({r.agent_id for r in rows}))} if rows else {}
    widgets = {w.id: w.name for w in db.query(ChatWidget).filter(ChatWidget.id.in_({r.widget_id for r in rows if r.widget_id}))} if rows else {}
    keys = {k.id: k.name for k in db.query(ApiKey).filter(ApiKey.id.in_({r.api_key_id for r in rows if r.api_key_id}))} if rows else {}
    leads = {lead.id: lead.name for lead in db.query(Lead).filter(Lead.id.in_({r.lead_id for r in rows if r.lead_id}))} if rows else {}
    out = []
    for r in rows:
        source = widgets.get(r.widget_id) if r.widget_id else (f"API: {keys[r.api_key_id]}" if r.api_key_id in keys else "API")
        turns = [ChatTurnOut(role=t["role"], text=t["text"]) for t in (r.turns or [])]
        out.append(ChatSessionOut(id=r.id, source=source or "Website chat", agent_name=agents.get(r.agent_id, "(deleted)"),
                                  origin=r.origin, lead_id=r.lead_id, lead_name=leads.get(r.lead_id or ""),
                                  messages=sum(1 for t in turns if t.role == "caller"), turns=turns,
                                  created_at=r.created_at, updated_at=r.updated_at))
    return out


# --- Public API ----------------------------------------------------------------------------------
# CORS for these routes is decided per request (app/core/cors.py leaves them alone): a widget request gets its
# own origin echoed back only after the widget key and origin check out, errors included, so the widget can show
# them; API-key requests get no CORS headers.

class PublicChatIn(BaseModel):
    message: str
    session: Optional[str] = Field(default=None, max_length=100)
    agent_id: Optional[str] = Field(default=None, max_length=50)


class PublicChatOut(BaseModel):
    session: Optional[str] = None
    reply: str
    ask_for_contact: bool


class PublicContactIn(BaseModel):
    session: str = Field(max_length=100)
    name: str = Field(min_length=1, max_length=100)
    phone: str
    email: Optional[EmailStr] = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class PublicVoiceIn(BaseModel):
    session: Optional[str] = Field(default=None, max_length=100)


_CORS_ALLOW_HEADERS = "Content-Type, X-Widget-Key"
MAX_PUBLIC_BODY = 16 * 1024


def _cors_headers(origin: Optional[str]) -> dict[str, str]:
    if not origin:
        return {}
    return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}


def _reply(content: Any, origin: Optional[str], status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=content, status_code=status_code, headers=_cors_headers(origin))


def _authenticate(request: Request, db: Session) -> public_chat.Caller:
    return public_chat.authenticate(db, widget_key=request.headers.get("x-widget-key"),
                                    authorization=request.headers.get("authorization"), origin=request.headers.get("origin"))


async def _body(request: Request, model: type[BaseModel]) -> Any:
    raw = await request.body()
    if len(raw) > MAX_PUBLIC_BODY:
        raise public_chat.PublicChatError("Request too large.", 413)
    try:
        return model.model_validate_json(raw or b"{}")
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][-1] if first["loc"] else "body"
        raise public_chat.PublicChatError(f"{field}: {first['msg'].removeprefix('Value error, ')}", 422)


def _error(exc: public_chat.PublicChatError, request: Request, allowed_origin: Optional[str]) -> JSONResponse:
    return _reply({"detail": str(exc)}, allowed_origin, exc.status_code)


@public_router.options("/api/public/{path:path}", include_in_schema=False)
def public_preflight(path: str, request: Request):
    """Browsers ask before sending the widget key. Any origin may ask; the real request is checked."""
    origin = request.headers.get("origin")
    headers = {"Access-Control-Allow-Methods": "GET, POST", "Access-Control-Allow-Headers": _CORS_ALLOW_HEADERS,
               "Access-Control-Max-Age": "600", **_cors_headers(origin)}
    return Response(status_code=204, headers=headers)


@public_router.get("/api/public/widget")
async def public_widget_config(request: Request, db: Session = Depends(get_db)):
    """What the widget shows before the first message. Widget key only."""
    caller = None
    try:
        caller = _authenticate(request, db)
        if caller.widget is None:
            raise public_chat.PublicChatError("This endpoint is for website widgets.", 400)
        return _reply(public_chat.widget_config(db, caller), caller.origin)
    except public_chat.PublicChatError as exc:
        return _error(exc, request, caller.origin if caller else None)


@public_router.post("/api/public/chat", response_model=PublicChatOut)
async def public_chat_message(request: Request, db: Session = Depends(get_db)):
    """Send the visitor's message and get the agent's reply. Leave out `session` to start a conversation; the reply
    carries its token, which later messages send back. API-key callers name the agent with `agent_id`."""
    from app.core.runtime_config import load_runtime_config
    caller = None
    try:
        caller = _authenticate(request, db)
        body = await _body(request, PublicChatIn)
        public_chat.throttle(caller, audit.client_ip(request))
        return _reply(public_chat.send(db, caller, body.message, body.session, body.agent_id, load_runtime_config()),
                      caller.origin)
    except public_chat.PublicChatError as exc:
        db.rollback()
        return _error(exc, request, caller.origin if caller else None)


@public_router.post("/api/public/chat/contact")
async def public_chat_contact(request: Request, db: Session = Depends(get_db)):
    """The visitor's name and phone (and email), saved as a CRM lead with the conversation so far."""
    caller = None
    try:
        caller = _authenticate(request, db)
        body = await _body(request, PublicContactIn)
        public_chat.throttle(caller, audit.client_ip(request), kind="contact", per_ip=5)
        return _reply(public_chat.capture_lead(db, caller, body.session, body.name.strip(), body.phone, body.email),
                      caller.origin)
    except public_chat.PublicChatError as exc:
        db.rollback()
        return _error(exc, request, caller.origin if caller else None)


@public_router.post("/api/public/voice")
async def public_voice(request: Request, db: Session = Depends(get_db)):
    """Start a browser voice call with the agent (widgets with voice turned on)."""
    from app.core.runtime_config import load_runtime_config
    caller = None
    try:
        caller = _authenticate(request, db)
        body = await _body(request, PublicVoiceIn)
        public_chat.throttle(caller, audit.client_ip(request), kind="voice", per_ip=public_chat.VOICE_PER_IP_PER_HOUR,
                             window=3600)
        return _reply(await public_chat.start_voice(db, caller, body.session, load_runtime_config()), caller.origin)
    except public_chat.PublicChatError as exc:
        db.rollback()
        return _error(exc, request, caller.origin if caller else None)


@public_router.get("/widget.js", include_in_schema=False)
def widget_script():
    return Response(content=WIDGET_JS.read_text(encoding="utf-8"), media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=300", "Cross-Origin-Resource-Policy": "cross-origin"})
