"""Outbound email. Resend when RESEND_API_KEY + EMAIL_FROM are set; logged locally otherwise."""
from __future__ import annotations

import logging

import httpx

from app.core.settings import settings

logger = logging.getLogger("mailer")


class EmailNotConfiguredError(RuntimeError):
    pass


def send_email(to: str, subject: str, text: str) -> str:
    """Send an email. Returns "sent" or "logged" (local dev without a provider).
    Raises EmailNotConfiguredError outside local when no provider is configured."""
    if settings.email_configured:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to], "subject": subject, "text": text},
            timeout=10.0,
        )
        response.raise_for_status()
        return "sent"
    if settings.is_local:
        logger.warning("[DEV EMAIL] Not sent (no provider configured).\nTo: %s\nSubject: %s\n\n%s", to, subject, text)
        return "logged"
    raise EmailNotConfiguredError("Email provider not configured (set RESEND_API_KEY and EMAIL_FROM).")


def deliver(to: str, subject: str, text: str) -> str:
    """Send without raising. Returns sent | logged | not_configured | failed, so auth flows never break on email."""
    try:
        return send_email(to, subject, text)
    except EmailNotConfiguredError:
        logger.error("Email not configured; could not send '%s' to %s", subject, to)
        return "not_configured"
    except Exception as exc:  # provider or network failure
        logger.error("Email to %s failed: %s", to, exc)
        return "failed"
