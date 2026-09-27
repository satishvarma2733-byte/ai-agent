"""Website chat and the public chat API.

Two ways in:
- A widget key ("wk_…") from a website. It is public (it sits in the page), so a request counts only when the
  browser's Origin is one the workspace listed for that widget.
- A secret API key ("avn_sk_…") from the workspace's own server. It is never answered with CORS headers, so it
  can't be used from a browser by accident.

Replies come from the agent's production version, through the same text model and brief as Agent Studio.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.security import hash_token, new_opaque_token
from app.core.tenancy import bind_session_to_tenant
from app.models.agent import Agent, AgentVersion
from app.models.lead import Lead, LeadActivity
from app.models.widget import ApiKey, ChatSession, ChatWidget

logger = logging.getLogger("public-chat")

WIDGET_KEY_PREFIX = "wk_"
API_KEY_PREFIX = "avn_sk_"
MAX_MESSAGE_CHARS = 1000
MAX_VISITOR_MESSAGES = 30
HISTORY_TURNS = 20  # what the model sees of a long conversation
PER_IP_PER_MINUTE = 20
PER_SOURCE_PER_MINUTE = 300
VOICE_PER_IP_PER_HOUR = 6
MAX_ORIGINS = 20
_LOCAL_HOSTS = ("localhost", "127.0.0.1")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class PublicChatError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_widget_key() -> str:
    return WIDGET_KEY_PREFIX + new_opaque_token()[:32]


def new_api_key() -> str:
    return API_KEY_PREFIX + new_opaque_token()


def normalize_origin(value: str) -> str:
    """"https://Example.com/" -> "https://example.com". Plain http only for localhost, for trying it out."""
    raw = str(value or "").strip().rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.path or parts.query or parts.fragment \
            or parts.username or parts.password:
        raise PublicChatError(f"'{value}' isn't a website origin. Use the form https://www.example.com", 422)
    if parts.scheme == "http" and parts.hostname not in _LOCAL_HOSTS:
        raise PublicChatError(f"'{value}' must use https (plain http is allowed only for localhost).", 422)
    host = parts.hostname.lower()
    return f"{parts.scheme}://{host}" + (f":{parts.port}" if parts.port else "")


def normalize_origins(values: list[str]) -> list[str]:
    origins = list(dict.fromkeys(normalize_origin(v) for v in values if str(v or "").strip()))
    if not origins:
        raise PublicChatError("List at least one website the widget will be on, like https://www.example.com", 422)
    if len(origins) > MAX_ORIGINS:
        raise PublicChatError(f"List at most {MAX_ORIGINS} websites.", 422)
    return origins


def check_color(value: str) -> str:
    if not _HEX_COLOR.match(value or ""):
        raise PublicChatError("Use a hex colour like #7B61FF.", 422)
    return value.upper()


@dataclass
class Caller:
    """Who is calling the public API, after the key (and origin) checked out."""
    tenant_id: str
    widget: ChatWidget | None
    api_key: ApiKey | None
    origin: str | None  # set only for widget requests; the response echoes it in CORS headers

    @property
    def source_id(self) -> str:
        return self.widget.id if self.widget else self.api_key.id  # type: ignore[union-attr]


def authenticate(db: Session, *, widget_key: str | None, authorization: str | None, origin: str | None) -> Caller:
    if authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:].strip()
        row = db.query(ApiKey).filter(ApiKey.key_hash == hash_token(key)).first() if key.startswith(API_KEY_PREFIX) else None
        if row is None or row.revoked_at is not None:
            raise PublicChatError("Invalid API key.", 401)
        bind_session_to_tenant(db, row.tenant_id)
        row.last_used_at = _now()
        return Caller(tenant_id=row.tenant_id, widget=None, api_key=row, origin=None)
    if widget_key:
        widget = db.query(ChatWidget).filter(ChatWidget.public_key == widget_key).first()
        if widget is None or not widget.enabled:
            raise PublicChatError("This chat isn't available.", 404)
        try:
            normalized = normalize_origin(origin or "")
        except PublicChatError:
            normalized = None
        if normalized is None or normalized not in (widget.allowed_origins or []):
            raise PublicChatError("This website isn't allowed to use this chat.", 403)
        bind_session_to_tenant(db, widget.tenant_id)
        return Caller(tenant_id=widget.tenant_id, widget=widget, api_key=None, origin=normalized)
    raise PublicChatError("Send a widget key (X-Widget-Key) or an API key (Authorization: Bearer).", 401)


def throttle(caller: Caller, ip: str | None, kind: str = "chat", per_ip: int | None = None,
             window: int = 60) -> None:
    per_ip = per_ip or PER_IP_PER_MINUTE
    keys = [(f"pub-{kind}:{caller.source_id}", PER_SOURCE_PER_MINUTE if kind == "chat" else per_ip * 20)]
    if ip:
        keys.append((f"pub-{kind}:{caller.source_id}:{ip}", per_ip))
    for key, limit in keys:
        if ratelimit.is_limited(key, limit, window):
            raise PublicChatError("Too many messages. Please wait a moment.", 429)
    for key, _ in keys:
        ratelimit.hit(key, window)


def live_agent(db: Session, caller: Caller, agent_id: str | None) -> tuple[Agent, AgentVersion]:
    agent_id = caller.widget.agent_id if caller.widget else agent_id
    if not agent_id:
        raise PublicChatError("Say which agent to talk to (agent_id).", 422)
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.tenant_id == caller.tenant_id).first()
    if agent is None:
        raise PublicChatError("Agent not found.", 404)
    version = db.get(AgentVersion, agent.production_version_id) if agent.production_version_id else None
    if agent.disabled_at is not None or version is None:
        raise PublicChatError("This assistant isn't live right now.", 503)
    return agent, version


def open_session(db: Session, caller: Caller, token: str | None, agent_id: str | None) -> tuple[ChatSession, str | None]:
    """The visitor's conversation, or a new one. Returns the session and, for a new one, its token."""
    if token:
        row = db.query(ChatSession).filter(ChatSession.token_hash == hash_token(token),
                                           ChatSession.tenant_id == caller.tenant_id).first()
        if row is None or (caller.widget and row.widget_id != caller.widget.id) \
                or (caller.api_key and row.api_key_id != caller.api_key.id):
            raise PublicChatError("That conversation has ended. Start a new one.", 404)
        return row, None
    agent, _ = live_agent(db, caller, agent_id)
    token = new_opaque_token()
    row = ChatSession(tenant_id=caller.tenant_id, agent_id=agent.id, widget_id=caller.widget.id if caller.widget else None,
                      api_key_id=caller.api_key.id if caller.api_key else None, token_hash=hash_token(token), turns=[],
                      origin=caller.origin, created_at=_now(), updated_at=_now())
    db.add(row)
    db.flush()
    return row, token


def _greeting(widget: ChatWidget | None, version: AgentVersion) -> str:
    if widget and widget.greeting:
        return widget.greeting
    cfg = version.config or {}
    lang = (cfg.get("languages") or {}).get("default") or "en"
    return str((cfg.get("greetings") or {}).get(lang) or "Hi! How can I help you today?")


def widget_config(db: Session, caller: Caller) -> dict[str, Any]:
    widget = caller.widget
    assert widget is not None
    agent, version = live_agent(db, caller, None)
    return {"name": widget.name, "agent_name": agent.name, "greeting": _greeting(widget, version), "color": widget.color,
            "voice": widget.voice_enabled, "lead_capture": widget.lead_capture}


def send(db: Session, caller: Caller, message: str, token: str | None, agent_id: str | None, config: dict) -> dict:
    from app.services import agent_testing
    message = str(message or "").strip()
    if not message:
        raise PublicChatError("Type a message.", 422)
    if len(message) > MAX_MESSAGE_CHARS:
        raise PublicChatError(f"Keep messages under {MAX_MESSAGE_CHARS} characters.", 422)
    session, new_token = open_session(db, caller, token, agent_id)
    turns = list(session.turns or [])
    if sum(1 for t in turns if t["role"] == "caller") >= MAX_VISITOR_MESSAGES:
        raise PublicChatError("This conversation is at its limit. Start a new one to keep chatting.", 429)
    agent, version = live_agent(db, caller, session.agent_id)
    turns.append({"role": "caller", "text": message, "at": _now().isoformat()})
    history = [{"role": t["role"], "text": t["text"]} for t in turns[-HISTORY_TURNS:]]
    try:
        answer = agent_testing.reply(version, caller.tenant_id, history, config)
    except agent_testing.AgentTestError as exc:
        logger.warning("[PUBLIC-CHAT] No reply for %s: %s", session.id, exc)
        raise PublicChatError("Sorry, the assistant can't answer right now. Please try again shortly.",
                              503 if exc.status_code >= 500 else exc.status_code) from exc
    turns.append({"role": "agent", "text": answer, "at": _now().isoformat()})
    session.turns = turns
    session.updated_at = _now()
    db.commit()
    visitor_messages = sum(1 for t in turns if t["role"] == "caller")
    ask_contact = bool(caller.widget and caller.widget.lead_capture and not session.lead_id and visitor_messages >= 2)
    return {"session": new_token, "reply": answer, "ask_for_contact": ask_contact}


def transcript_text(turns: list[dict]) -> str:
    return "\n".join(f"{'Visitor' if t['role'] == 'caller' else 'Assistant'}: {t['text']}" for t in turns)[:5000]


def capture_lead(db: Session, caller: Caller, token: str, name: str, phone: str, email: str | None) -> dict:
    """Attach the visitor's contact details to the conversation as a CRM lead (new, or an existing one by phone)."""
    from app.services import workflow_events
    session, _ = open_session(db, caller, token, None)
    lead = db.query(Lead).filter(Lead.tenant_id == caller.tenant_id, Lead.phone == phone, Lead.deleted_at == None).first()  # noqa: E711
    created = lead is None
    if created:
        lead = Lead(tenant_id=caller.tenant_id, name=name, phone=phone, email=email, status="New", score="Warm",
                    notes="Came in through the website chat.")
        db.add(lead)
    else:
        lead.email = lead.email or email
    db.flush()
    where = caller.widget.name if caller.widget else (caller.api_key.name if caller.api_key else "the chat API")
    db.add(LeadActivity(lead_id=lead.id, tenant_id=caller.tenant_id, activity_type="chat",
                        title=f"Website chat ({where})",
                        description=transcript_text(session.turns or []) or "Left contact details in the chat."))
    session.lead_id = lead.id
    session.updated_at = _now()
    db.commit()
    if created:
        workflow_events.emit(db, caller.tenant_id, "lead_created", lead_id=lead.id)
    return {"lead_id": lead.id, "created": created}


VOICE_TTL_MINUTES = 15


async def start_voice(db: Session, caller: Caller, token: str | None, config: dict) -> dict:
    """A LiveKit room where the visitor talks to the production agent through the browser. The call is logged
    like any other (direction "web") and counts toward the plan's minutes."""
    import json
    import secrets
    from datetime import timedelta

    from livekit import api

    from app.services import plan_limits
    from outbound_calls import DEFAULT_AGENT_NAME, get_livekit_settings
    if caller.widget is None or not caller.widget.voice_enabled:
        raise PublicChatError("Voice isn't turned on for this chat.", 403)
    session, new_token = open_session(db, caller, token, None)
    agent, _ = live_agent(db, caller, session.agent_id)
    tenant = plan_limits._tenant(db, caller.tenant_id)
    if plan_limits.usage(db, tenant).outbound_blocked:
        raise PublicChatError("Voice chat is unavailable right now. You can still type.", 503)
    settings = get_livekit_settings(config)
    if not (settings["url"] and settings["api_key"] and settings["api_secret"]):
        raise PublicChatError("Voice chat is unavailable right now. You can still type.", 503)
    db.commit()
    room = f"web-{secrets.token_hex(8)}"
    lk = api.LiveKitAPI(url=settings["url"], api_key=settings["api_key"], api_secret=settings["api_secret"])
    try:
        await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
            agent_name=DEFAULT_AGENT_NAME, room=room,
            metadata=json.dumps({"tenant_id": caller.tenant_id, "agent_id": agent.id, "channel": "web",
                                 "chat_session_id": session.id})))
    except api.TwirpError as exc:
        logger.error("[PUBLIC-VOICE] Dispatch failed: %s", exc.message)
        raise PublicChatError("Voice chat is unavailable right now. You can still type.", 502) from exc
    finally:
        await lk.aclose()
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True, can_publish_data=False)
    jwt = (api.AccessToken(settings["api_key"], settings["api_secret"]).with_identity(f"visitor-{secrets.token_hex(6)}")
           .with_name("Website visitor").with_grants(grants).with_ttl(timedelta(minutes=VOICE_TTL_MINUTES)).to_jwt())
    return {"url": settings["url"], "token": jwt, "room": room, "session": new_token}
