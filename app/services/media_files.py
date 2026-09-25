"""Uploaded CMS media: which files are accepted, where they are stored, and how they are served.

Only passive formats (images, audio, PDF) are accepted, identified by their content signature, not the
client's filename or content type. Files are served with a fixed content type, `nosniff`, and a sandboxing
CSP so nothing uploaded can run script on the API origin.
"""
from __future__ import annotations

import re
from pathlib import Path

MEDIA_ROOT = Path("data") / "media"
MAX_MEDIA_BYTES = 15 * 1024 * 1024

# extension -> served content type
ALLOWED_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
}
STORED_NAME = re.compile(r"^[0-9a-f]{32}\.(png|jpg|gif|webp|pdf|mp3|wav|ogg|m4a)$")
TENANT_DIR = re.compile(r"^[0-9a-fA-F-]{8,50}$")


def detect_type(data: bytes) -> str | None:
    """Extension for the file's real format, or None if it isn't an allowed passive format."""
    head = data[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if head.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if head.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return ".wav"
    if head.startswith(b"%PDF-"):
        return ".pdf"
    if head.startswith(b"OggS"):
        return ".ogg"
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return ".mp3"
    if data[4:8] == b"ftyp" and data[8:11] in (b"M4A", b"mp4", b"iso", b"M4B"):
        return ".m4a"
    return None


def resolve(tenant_id: str, name: str) -> Path | None:
    """Path of a stored file, or None for anything that isn't a well-formed stored name."""
    if not TENANT_DIR.match(tenant_id) or not STORED_NAME.match(name):
        return None
    path = MEDIA_ROOT / tenant_id / name
    return path if path.is_file() else None
