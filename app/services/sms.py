"""Text messages (SMS) for a workspace through Twilio: reminders and follow-ups from workflows.

Each workspace connects its own Twilio account and SMS-capable number; credentials are checked with Twilio and
stored encrypted. Sent messages are recorded on the lead's timeline. In India, business SMS also needs DLT
registration of the sender and templates, which happens in Twilio and with the operator, not here.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

import config_crypto
from app.core.settings import settings
from app.models.lead import Lead, LeadActivity
from app.models.sms import SmsAccount

logger = logging.getLogger("sms")

TWILIO_API = "https://api.twilio.com/2010-04-01"
TIMEOUT = 15
MAX_CHARS = 1000  # about 7 SMS segments


class SmsNotConnected(Exception):
    pass


class SmsError(Exception):
    pass


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
        raise config_crypto.SecretsKeyError("Set SECRETS_ENCRYPTION_KEY before connecting SMS.")


def _normalize(phone: str) -> str:
    from app.schemas.lead import normalize_phone
    return normalize_phone(phone)


def _twilio_error(res: httpx.Response) -> str:
    try:
        return str(res.json().get("message") or f"HTTP {res.status_code}")
    except ValueError:
        return f"HTTP {res.status_code}"


def save_account(db: Session, tenant_id: str, user_id: str, account_sid: str, auth_token: str, from_number: str) -> SmsAccount:
    if not (account_sid.strip() and auth_token.strip() and from_number.strip()):
        raise SmsError("Account SID, auth token and the sending number are all required.")
    try:
        sender = _normalize(from_number)
    except ValueError as exc:
        raise SmsError(f"Sending number: {exc}") from exc
    with http() as client:
        res = client.get(f"{TWILIO_API}/Accounts/{account_sid.strip()}.json", auth=(account_sid.strip(), auth_token.strip()))
    if res.status_code != 200:
        raise SmsError(f"Twilio rejected these details: {_twilio_error(res)}")
    account = db.query(SmsAccount).filter(SmsAccount.tenant_id == tenant_id).first()
    if account is None:
        account = SmsAccount(tenant_id=tenant_id, created_at=_now())
        db.add(account)
    account.provider, account.sender = "twilio", sender
    account.credentials = _seal({"account_sid": account_sid.strip(), "auth_token": auth_token.strip()})
    account.connected_by, account.updated_at = user_id, _now()
    db.commit()
    return account


def send(db: Session, tenant_id: str, phone: str, text: str, *, lead: Lead | None = None, source: str = "manual") -> str:
    """Send one SMS and note it on the lead's timeline. Returns Twilio's message id."""
    account = db.query(SmsAccount).filter(SmsAccount.tenant_id == tenant_id).first()
    if account is None:
        raise SmsNotConnected("SMS is not connected yet. No message was sent.")
    body = (text or "").strip()
    if not body:
        raise SmsError("Nothing to send.")
    if len(body) > MAX_CHARS:
        raise SmsError(f"Keep text messages under {MAX_CHARS} characters.")
    try:
        to = _normalize(phone)
    except ValueError as exc:
        raise SmsError(str(exc)) from exc
    creds = _open(account.credentials)
    error = None
    sid = None
    try:
        with http() as client:
            res = client.post(f"{TWILIO_API}/Accounts/{creds['account_sid']}/Messages.json",
                              data={"From": account.sender, "To": to, "Body": body},
                              auth=(creds["account_sid"], creds["auth_token"]))
        if res.status_code >= 400:
            error = _twilio_error(res)
        else:
            sid = res.json().get("sid")
    except httpx.HTTPError as exc:
        error = f"Couldn't reach Twilio: {exc}"
    if lead is not None:
        db.add(LeadActivity(lead_id=lead.id, tenant_id=tenant_id, activity_type="sms",
                            title="SMS sent" if error is None else "SMS failed",
                            description=(body if error is None else f"{body}\n\n{error}")[:1000]))
        db.commit()
    if error:
        raise SmsError(error)
    return sid or ""
