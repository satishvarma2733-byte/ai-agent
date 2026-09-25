"""WhatsApp for a workspace, through Meta's Cloud API or Twilio.

Each workspace connects its own sender. Messages are logged with the delivery status the provider
reports back to the workspace's webhook URL, and replies from customers land on the lead's timeline.
WhatsApp only allows free text within 24 hours of the customer's last message; anything else must be an
approved template (Meta: the template's name; Twilio: its Content SID, "HX…").
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

import config_crypto
from app.core.security import hash_token, new_opaque_token
from app.core.settings import settings
from app.models.lead import Lead, LeadActivity
from app.models.whatsapp import WhatsAppAccount, WhatsAppMessage

logger = logging.getLogger("whatsapp")

META_API = "https://graph.facebook.com/v21.0"
TWILIO_API = "https://api.twilio.com/2010-04-01"
TIMEOUT = 15
PROVIDERS = ("meta", "twilio")
# Later statuses never go back to earlier ones when webhooks arrive out of order.
_STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 2}
_WINDOW_CLOSED = ("WhatsApp only allows free text within 24 hours of the customer's last message. "
                  "Send an approved template instead.")


class WhatsAppNotConnected(Exception):
    pass


class WhatsAppError(Exception):
    pass


@dataclass
class Template:
    name: str  # Meta template name, or Twilio Content SID
    language: str = "en"
    params: tuple[str, ...] = ()


def http() -> httpx.Client:
    """One client per call; tests replace this to intercept requests."""
    return httpx.Client(timeout=TIMEOUT)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seal(data: dict) -> str:
    raw = json.dumps(data)
    return config_crypto.encrypt(raw) if config_crypto.encryption_available() else raw


def _open(stored: str) -> dict:
    return json.loads(config_crypto.decrypt(stored))


def ensure_can_store_credentials() -> None:
    if not config_crypto.encryption_available() and not settings.is_local:
        raise config_crypto.SecretsKeyError("Set SECRETS_ENCRYPTION_KEY before connecting WhatsApp.")


def normalize(phone: str) -> str:
    from app.schemas.lead import normalize_phone
    return normalize_phone(phone.removeprefix("whatsapp:").strip())


# --- Connecting ----------------------------------------------------------------------------------

REQUIRED = {
    "meta": ("phone_number_id", "access_token", "app_secret"),
    "twilio": ("account_sid", "auth_token", "from_number"),
}


def verify_credentials(provider: str, creds: dict) -> str:
    """Check the credentials with the provider and return the sender number to show."""
    missing = [k for k in REQUIRED[provider] if not str(creds.get(k) or "").strip()]
    if missing:
        raise WhatsAppError(f"Missing {', '.join(missing)}.")
    with http() as client:
        if provider == "meta":
            res = client.get(f"{META_API}/{creds['phone_number_id']}", params={"fields": "display_phone_number,verified_name"},
                             headers={"Authorization": f"Bearer {creds['access_token']}"})
            if res.status_code != 200:
                raise WhatsAppError(f"Meta rejected these details: {_meta_error(res)}")
            return str(res.json().get("display_phone_number") or creds["phone_number_id"])
        try:
            sender = normalize(creds["from_number"])
        except ValueError as exc:
            raise WhatsAppError(f"WhatsApp number: {exc}") from exc
        res = client.get(f"{TWILIO_API}/Accounts/{creds['account_sid']}.json", auth=(creds["account_sid"], creds["auth_token"]))
        if res.status_code != 200:
            raise WhatsAppError(f"Twilio rejected these details: {_twilio_error(res)}")
        return sender


def save_account(db: Session, tenant_id: str, user_id: str, provider: str, creds: dict) -> WhatsAppAccount:
    sender = verify_credentials(provider, creds)
    keep = {k: str(creds[k]).strip() for k in REQUIRED[provider]}
    if provider == "twilio":
        keep["from_number"] = sender
    account = db.query(WhatsAppAccount).filter(WhatsAppAccount.tenant_id == tenant_id).first()
    if account is None:
        token = new_opaque_token()
        account = WhatsAppAccount(tenant_id=tenant_id, created_at=_now(), webhook_token_hash=hash_token(token),
                                  webhook_token=config_crypto.encrypt(token) if config_crypto.encryption_available() else token)
        db.add(account)
    account.provider, account.sender, account.credentials = provider, sender, _seal(keep)
    account.status, account.last_error, account.connected_by, account.updated_at = "active", None, user_id, _now()
    db.commit()
    return account


def webhook_token(account: WhatsAppAccount) -> str:
    return config_crypto.decrypt(account.webhook_token)


def webhook_url(account: WhatsAppAccount, request_base: str) -> str:
    base = (settings.public_api_url or request_base).rstrip("/")
    return f"{base}/api/whatsapp/webhook/{account.provider}/{webhook_token(account)}"


def account_for_token(db: Session, provider: str, token: str) -> WhatsAppAccount | None:
    account = db.query(WhatsAppAccount).filter(WhatsAppAccount.webhook_token_hash == hash_token(token)).first()
    return account if account is not None and account.provider == provider else None


# --- Sending -------------------------------------------------------------------------------------

def render(text: str, lead: Lead | None, workspace_name: str = "", appointment=None) -> str:
    """Placeholders such as {{lead.first_name}}; see app.services.placeholders."""
    from app.services.placeholders import render as _render
    return _render(text, lead, workspace_name, appointment)


def send(db: Session, tenant_id: str, phone: str, *, text: str | None = None, template: Template | None = None,
         lead: Lead | None = None, source: str = "manual") -> WhatsAppMessage:
    """Send one message and log it. Raises WhatsAppNotConnected, or WhatsAppError with the provider's reason."""
    account = db.query(WhatsAppAccount).filter(WhatsAppAccount.tenant_id == tenant_id).first()
    if account is None:
        raise WhatsAppNotConnected("WhatsApp is not connected yet. No message was sent.")
    if not text and not template:
        raise WhatsAppError("Nothing to send.")
    try:
        to = normalize(phone)
    except ValueError as exc:
        raise WhatsAppError(str(exc)) from exc
    creds = _open(account.credentials)
    body = text if text else f"[template {template.name}] " + " | ".join(template.params)
    message = WhatsAppMessage(tenant_id=tenant_id, lead_id=lead.id if lead else None, phone=to, direction="out",
                              body=body[:4000], template=template.name if template else None, provider=account.provider,
                              status="failed", source=source, created_at=_now(), updated_at=_now())
    try:
        with http() as client:
            if account.provider == "meta":
                message.provider_message_id = _meta_send(client, creds, to, text, template)
            else:
                callback = webhook_url(account, "") if settings.public_api_url else None
                message.provider_message_id = _twilio_send(client, creds, to, text, template, callback)
        message.status = "sent"
    except WhatsAppError as exc:
        message.error = str(exc)[:500]
    except httpx.HTTPError as exc:
        message.error = f"Couldn't reach {account.provider}: {exc}"[:500]
    db.add(message)
    if lead is not None:
        db.add(LeadActivity(lead_id=lead.id, tenant_id=tenant_id, activity_type="whatsapp",
                            title="WhatsApp sent" if message.status == "sent" else "WhatsApp failed",
                            description=(body if message.status == "sent" else f"{body}\n\n{message.error}")[:1000]))
    db.commit()
    if message.status == "failed":
        raise WhatsAppError(message.error)
    return message


def _meta_send(client: httpx.Client, creds: dict, to: str, text: str | None, template: Template | None) -> str:
    payload: dict = {"messaging_product": "whatsapp", "to": to.lstrip("+")}
    if text:
        payload.update(type="text", text={"body": text, "preview_url": False})
    else:
        tpl: dict = {"name": template.name, "language": {"code": template.language or "en"}}
        if template.params:
            tpl["components"] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in template.params]}]
        payload.update(type="template", template=tpl)
    res = client.post(f"{META_API}/{creds['phone_number_id']}/messages", json=payload,
                      headers={"Authorization": f"Bearer {creds['access_token']}"})
    if res.status_code >= 400:
        raise WhatsAppError(_meta_error(res))
    return res.json()["messages"][0]["id"]


def _twilio_send(client: httpx.Client, creds: dict, to: str, text: str | None, template: Template | None,
                 callback: str | None) -> str:
    form = {"From": f"whatsapp:{creds['from_number']}", "To": f"whatsapp:{to}"}
    if text:
        form["Body"] = text
    else:
        form["ContentSid"] = template.name
        if template.params:
            form["ContentVariables"] = json.dumps({str(i + 1): p for i, p in enumerate(template.params)})
    if callback:
        form["StatusCallback"] = callback
    res = client.post(f"{TWILIO_API}/Accounts/{creds['account_sid']}/Messages.json", data=form,
                      auth=(creds["account_sid"], creds["auth_token"]))
    if res.status_code >= 400:
        raise WhatsAppError(_twilio_error(res))
    return res.json()["sid"]


def _meta_error(res: httpx.Response) -> str:
    try:
        err = res.json().get("error", {})
    except ValueError:
        return f"HTTP {res.status_code}"
    if err.get("code") == 131047:
        return _WINDOW_CLOSED
    detail = (err.get("error_data") or {}).get("details")
    return f"{err.get('message') or 'HTTP ' + str(res.status_code)}{' (' + detail + ')' if detail else ''}"


def _twilio_error(res: httpx.Response) -> str:
    try:
        body = res.json()
    except ValueError:
        return f"HTTP {res.status_code}"
    if body.get("code") == 63016:
        return _WINDOW_CLOSED
    return str(body.get("message") or f"HTTP {res.status_code}")


# --- Webhooks ------------------------------------------------------------------------------------

def meta_signature_ok(account: WhatsAppAccount, raw_body: bytes, header: str | None) -> bool:
    secret = _open(account.credentials).get("app_secret", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return bool(secret and header) and hmac.compare_digest(expected, header)


def twilio_signature_ok(account: WhatsAppAccount, url: str, params: dict, header: str | None) -> bool:
    """Twilio signs the full URL it called followed by each POST parameter name and value, sorted by name."""
    token = _open(account.credentials).get("auth_token", "")
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    expected = base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return bool(token and header) and hmac.compare_digest(expected, header)


def handle_meta(db: Session, account: WhatsAppAccount, payload: dict) -> int:
    handled = 0
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for status in value.get("statuses") or []:
                errors = status.get("errors") or []
                error = (errors[0].get("error_data") or {}).get("details") or errors[0].get("title") if errors else None
                handled += update_status(db, account, status.get("id"), status.get("status"), error)
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
            for msg in value.get("messages") or []:
                kind = msg.get("type")
                body = (msg.get("text") or {}).get("body") if kind == "text" else f"[{kind}]"
                handled += receive(db, account, "+" + str(msg.get("from", "")), body, msg.get("id"), names.get(msg.get("from")))
    return handled


def handle_twilio(db: Session, account: WhatsAppAccount, params: dict) -> int:
    status = params.get("MessageStatus")
    if status and status != "received":
        mapped = {"queued": "sent", "accepted": "sent", "sending": "sent", "undelivered": "failed"}.get(status, status)
        error = f"Twilio error {params['ErrorCode']}" if params.get("ErrorCode") else None
        return update_status(db, account, params.get("MessageSid"), mapped, error)
    if params.get("From"):
        body = params.get("Body") or (f"[{params.get('NumMedia')} attachment(s)]" if params.get("NumMedia") not in (None, "0") else "")
        return receive(db, account, params["From"], body, params.get("MessageSid"), params.get("ProfileName"))
    return 0


def update_status(db: Session, account: WhatsAppAccount, provider_id: str | None, status: str | None, error: str | None) -> int:
    if not provider_id or status not in _STATUS_RANK:
        return 0
    message = db.query(WhatsAppMessage).filter(WhatsAppMessage.tenant_id == account.tenant_id,
                                               WhatsAppMessage.provider_message_id == provider_id).first()
    if message is None or message.status == "read":
        return 0
    if status != "failed" and _STATUS_RANK[status] <= _STATUS_RANK.get(message.status, 0):
        return 0
    message.status, message.updated_at = status, _now()
    if error:
        message.error = str(error)[:500]
    db.commit()
    return 1


def receive(db: Session, account: WhatsAppAccount, phone: str, body: str | None, provider_id: str | None,
            profile_name: str | None) -> int:
    """A customer's message: log it once, put it on the lead's timeline (creating the lead if new) and tell the team."""
    from app.services import notifications, workflow_events
    try:
        phone = normalize(phone)
    except ValueError:
        return 0
    if provider_id and db.query(WhatsAppMessage.id).filter(WhatsAppMessage.tenant_id == account.tenant_id,
                                                           WhatsAppMessage.provider_message_id == provider_id).first():
        return 0  # a retried webhook
    lead = workflow_events.find_lead(db, account.tenant_id, phone)
    if lead is None:
        lead = Lead(tenant_id=account.tenant_id, name=profile_name or f"WhatsApp {phone}", phone=phone, status="New",
                    score="Cold", notes="Created from a WhatsApp message.")
        db.add(lead)
        db.flush()
    db.add(WhatsAppMessage(tenant_id=account.tenant_id, lead_id=lead.id, phone=phone, direction="in",
                           body=(body or "")[:4000], provider=account.provider, provider_message_id=provider_id,
                           status="received", source="inbound", created_at=_now(), updated_at=_now()))
    db.add(LeadActivity(lead_id=lead.id, tenant_id=account.tenant_id, activity_type="whatsapp",
                        title="WhatsApp received", description=(body or "")[:1000]))
    db.commit()
    recipients = [lead.assigned_user_id] if lead.assigned_user_id else notifications.managers(db, account.tenant_id)
    notifications.notify(db, account.tenant_id, recipients, kind="whatsapp_received",
                         title=f"WhatsApp from {lead.name}", body=(body or "")[:200], link="/crm")
    return 1
