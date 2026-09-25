"""Short-lived links for recordings the browser loads without the access token.

`<audio src>` can't send the Authorization header (the access token lives only in memory), so call-log
responses carry a recording link signed for one workspace and one file that stops working after an hour.
Recordings in the private Supabase bucket are served through the same link: the API checks the signature,
then redirects to a Supabase URL that is valid for a minute.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from urllib.parse import quote, urlencode

import httpx

from app.core.security import SECRET_KEY

RECORDING_LINK_TTL = 3600
STORAGE_LINK_TTL = 60
RECORDINGS_PATH = "/api/recordings/"
RECORDINGS_BUCKET = "call-recordings"
# What the voice worker stores for a recording uploaded to the bucket (the bucket is private).
STORAGE_PREFIX = f"supabase-storage://{RECORDINGS_BUCKET}/"
# Older rows stored the bucket's public URL.
_LEGACY_PUBLIC_MARKER = f"/storage/v1/object/public/{RECORDINGS_BUCKET}/"


def _signature(tenant_id: str, name: str, exp: int) -> str:
    key = f"recording-link:{SECRET_KEY}".encode()
    return hmac.new(key, f"{tenant_id}:{name}:{exp}".encode(), hashlib.sha256).hexdigest()


def recording_link(tenant_id: str, name: str, ttl: int = RECORDING_LINK_TTL) -> str:
    exp = int(time.time()) + ttl
    return f"{RECORDINGS_PATH}{name}?" + urlencode({"t": tenant_id, "exp": exp, "sig": _signature(tenant_id, name, exp)})


def verify_recording_link(tenant_id: str, name: str, exp: int, sig: str) -> bool:
    if exp < time.time():
        return False
    return hmac.compare_digest(_signature(tenant_id, name, exp), sig)


def storage_object_path(recording_url: str | None) -> str | None:
    """Object path inside the recordings bucket, for a stored reference or a legacy public URL."""
    if not recording_url:
        return None
    if recording_url.startswith(STORAGE_PREFIX):
        return recording_url[len(STORAGE_PREFIX):]
    if _LEGACY_PUBLIC_MARKER in recording_url:
        return recording_url.split(_LEGACY_PUBLIC_MARKER, 1)[1].split("?", 1)[0]
    return None


def sign_local_recording(tenant_id: str | None, recording_url: str | None) -> str | None:
    """Swap a stored recording location for a signed API link; any other URL passes through unchanged."""
    if not tenant_id or not recording_url:
        return recording_url
    if recording_url.startswith(RECORDINGS_PATH):
        name = recording_url[len(RECORDINGS_PATH):].split("?", 1)[0]
    elif (path := storage_object_path(recording_url)) is not None:
        name = path.rsplit("/", 1)[-1]
    else:
        return recording_url
    return recording_link(str(tenant_id), name)


def storage_download_url(object_path: str) -> str | None:
    """A Supabase URL for one object in the private bucket, valid for STORAGE_LINK_TTL seconds."""
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not base or not key:
        return None
    res = httpx.post(
        f"{base}/storage/v1/object/sign/{RECORDINGS_BUCKET}/{quote(object_path)}",
        headers={"Authorization": f"Bearer {key}", "apikey": key},
        json={"expiresIn": STORAGE_LINK_TTL},
        timeout=10,
    )
    if res.status_code != 200:
        return None
    signed = res.json().get("signedURL") or res.json().get("signedUrl")
    if not signed:
        return None
    return signed if signed.startswith("http") else f"{base}/storage/v1{signed}"
