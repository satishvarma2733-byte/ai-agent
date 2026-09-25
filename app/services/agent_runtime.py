"""Which agent (and workspace) handles a call, and the runtime settings from its production version.

Inbound calls are matched by the dialed business number; outbound calls name their agent in the
dispatch metadata. A call with no match keeps the shared default configuration."""
from __future__ import annotations

import logging
from typing import Any

from app.core.database import SessionLocal
from app.models.agent import Agent, AgentPhoneNumber, AgentVersion

logger = logging.getLogger("agent-runtime")


def canonical_number(value: str | None) -> str | None:
    """E.164 form used to store and match business numbers (SIP gives e.g. "919876543210" or "+91 98765 43210")."""
    from db_backend import normalize_phone_number
    from app.schemas.lead import normalize_phone
    try:
        return normalize_phone(normalize_phone_number(value))
    except ValueError:
        return None


def runtime_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Map an AgentVersion config onto the voice runtime's config keys."""
    languages = config.get("languages") or {}
    lang = languages.get("default") or "en"
    supported = languages.get("supported") or [lang]
    instructions = str(config.get("instructions") or "")
    greetings = config.get("greetings") or {}
    voice = config.get("voice") or {}
    llm = config.get("llm") or {}
    limits = config.get("limits") or {}
    overrides: dict[str, Any] = {
        "agent_instructions": instructions,
        "first_line": greetings.get(lang) or (instructions.split("\n")[0] if instructions else ""),
        "gemini_live_language": lang,
        "lang_preset": "multilingual" if len(supported) > 1 or lang != "en" else "en",
    }
    if voice.get("voice"):
        overrides["gemini_live_voice"] = voice["voice"]
    if voice.get("live_model"):
        overrides["gemini_live_model"] = voice["live_model"]
    if llm.get("temperature") is not None:
        overrides["gemini_live_temperature"] = llm["temperature"]
    if limits.get("max_call_seconds"):
        overrides["max_turns"] = max(5, int(limits["max_call_seconds"]) // 20)
    return {k: v for k, v in overrides.items() if v not in (None, "")}


def resolve_for_call(called_number: str | None = None, agent_id: str | None = None) -> dict[str, Any] | None:
    """{"tenant_id", "agent_id", "agent_name", "version", "overrides"} for the agent handling this call,
    or None when the call isn't routed to a specific agent (or the agent can't take calls)."""
    db = SessionLocal()
    try:
        agent = None
        if agent_id:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
        elif called_number:
            number = canonical_number(called_number)
            row = db.query(AgentPhoneNumber).filter(AgentPhoneNumber.phone_number == number).first() if number else None
            agent = db.query(Agent).filter(Agent.id == row.agent_id).first() if row else None
        if agent is None:
            return None
        if agent.disabled_at is not None:
            logger.warning("[ROUTING] Agent %s is disabled; using the default configuration", agent.id)
            return None
        version = db.query(AgentVersion).filter(AgentVersion.id == agent.production_version_id).first() \
            if agent.production_version_id else None
        if version is None:
            logger.warning("[ROUTING] Agent %s has no production version; using the default configuration", agent.id)
            return None
        return {
            "tenant_id": agent.tenant_id, "agent_id": agent.id, "agent_name": agent.name,
            "version": version.number, "overrides": runtime_overrides(version.config or {}),
        }
    finally:
        db.close()
