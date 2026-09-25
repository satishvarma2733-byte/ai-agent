"""Inbound lead webhooks and signed outbound webhook calls."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

import config_crypto
from app.core.settings import settings

OUTBOUND_TIMEOUT = 5.0
MAX_RESPONSE_LOG = 200


class UnsafeUrl(ValueError):
    pass


def check_public_url(url: str) -> str:
    """Allow only URLs whose host resolves exclusively to public addresses (blocks SSRF to the
    internal network and cloud metadata). HTTPS is required outside local development."""
    parsed = urlparse(str(url or "").strip())
    allowed = {"https"} if not settings.is_local else {"https", "http"}
    if parsed.scheme not in allowed or not parsed.hostname:
        raise UnsafeUrl("Use an https:// URL." if not settings.is_local else "Use an http(s):// URL.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        raise UnsafeUrl(f"Could not resolve {parsed.hostname}.")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UnsafeUrl("Webhook URLs must point to a public internet address.")
    return parsed.geturl()


def seal_secret(secret: str) -> str:
    """Encrypt at rest when a key is configured; local development may store it plain."""
    return config_crypto.encrypt(secret) if config_crypto.encryption_available() else secret


def open_secret(stored: str) -> str:
    return config_crypto.decrypt(stored)


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post_event(url: str, secret: str | None, event: str, payload: dict) -> str:
    """POST a signed JSON event. Returns a short description of the outcome (never raises for HTTP errors)."""
    target = check_public_url(url)
    body = json.dumps({"event": event, "sent_at": datetime.now(timezone.utc).isoformat(), **payload}, default=str).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "aVn-Webhooks/1", "X-AVN-Event": event}
    if secret:
        headers["X-AVN-Signature"] = sign(secret, body)
    try:
        # No redirects: a redirect could point back into the internal network.
        response = httpx.post(target, content=body, headers=headers, timeout=OUTBOUND_TIMEOUT, follow_redirects=False)
    except httpx.HTTPError as exc:
        return f"webhook failed: {type(exc).__name__}"
    return f"webhook answered {response.status_code}"
