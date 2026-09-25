"""Encryption for credentials stored in runtime config files (Fernet: AES-128-CBC + HMAC-SHA256).

Key: SECRETS_ENCRYPTION_KEY, generated with
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Encrypted values are stored as "enc:v1:<token>" so plain-text values from older files still load.
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:v1:"


class SecretsKeyError(RuntimeError):
    pass


def _fernet() -> Fernet | None:
    key = os.getenv("SECRETS_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise SecretsKeyError("SECRETS_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def encryption_available() -> bool:
    return _fernet() is not None


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value: str) -> str:
    if not value or is_encrypted(value):
        return value
    fernet = _fernet()
    if fernet is None:
        raise SecretsKeyError("SECRETS_ENCRYPTION_KEY is required to store credentials.")
    return PREFIX + fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not is_encrypted(value):
        return value
    fernet = _fernet()
    if fernet is None:
        raise SecretsKeyError("Config contains encrypted credentials but SECRETS_ENCRYPTION_KEY is not set.")
    try:
        return fernet.decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise SecretsKeyError("Could not decrypt a stored credential: SECRETS_ENCRYPTION_KEY does not match.") from exc
