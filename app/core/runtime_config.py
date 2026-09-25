"""Runtime (voice/LiveKit/Gemini/KB) configuration shared by the API and workers.

Wraps the file-based config in `backend_config` so routers no longer import the
legacy `backend_api` module.
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from backend_config import SECRET_CONFIG_KEYS, apply_config_env, read_config, write_config

MAX_KB_UPLOAD_BYTES = 25 * 1024 * 1024

_MASK_PREFIX = "••••"


def load_runtime_config(phone_number: str | None = None) -> dict[str, Any]:
    config = read_config(phone_number)
    apply_config_env(config)
    return config


def mask_secret(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return f"{_MASK_PREFIX}{text[-4:]}" if len(text) > 8 else _MASK_PREFIX


def public_config() -> dict[str, Any]:
    """Config safe to send to a browser: secrets masked, presence still visible."""
    config = read_config()
    return {
        key: (mask_secret(value) if key in SECRET_CONFIG_KEYS else value)
        for key, value in config.items()
    }


def update_config(data: dict[str, Any]) -> dict[str, Any]:
    """Persist config changes. Masked secret values echoed back by the UI are ignored."""
    cleaned = {
        key: value for key, value in data.items()
        if not (key in SECRET_CONFIG_KEYS and isinstance(value, str) and value.startswith(_MASK_PREFIX))
    }
    updated = write_config(cleaned)
    apply_config_env(updated)
    return updated


def internal_error_response(
    public_message: str = "Unable to complete the request right now.",
    *,
    status_code: int = 500,
) -> JSONResponse:
    return JSONResponse({"status": "error", "message": public_message}, status_code=status_code)
