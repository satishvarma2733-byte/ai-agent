"""Agent versions: drafts, validated edits with a change log, and lifecycle transitions.

Production configuration is never edited in place. Every edit goes to the agent's single draft;
a draft becomes production only through submit → evaluate → approve → activate.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent import Agent, AgentChange, AgentLifecycleEvent, AgentVersion
from app.models.user import User
from app.schemas.agent_config import AgentConfig
from app.services.auth_service import utcnow


class AgentError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


# action: (allowed from statuses, to status, minimum role)
TRANSITIONS: dict[str, tuple[frozenset[str], str, str]] = {
    "submit":   (frozenset({"draft"}), "testing", "Manager"),
    "evaluate": (frozenset({"testing"}), "evaluation", "Manager"),
    "approve":  (frozenset({"evaluation"}), "approved", "Admin"),
    "reject":   (frozenset({"testing", "evaluation", "approved"}), "rejected", "Manager"),
    "activate": (frozenset({"approved"}), "production", "Admin"),
    "rollback": (frozenset({"superseded"}), "production", "Admin"),
}


# ── Config helpers ───────────────────────────────────────────────────
def default_config() -> dict[str, Any]:
    return AgentConfig().model_dump()


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    try:
        return AgentConfig.model_validate(config).model_dump()
    except ValidationError as exc:
        first = exc.errors()[0]
        path = ".".join(str(p) for p in first["loc"])
        raise AgentError(f"Invalid agent configuration at '{path}': {first['msg']}", status_code=422) from exc


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Nested dicts merge; everything else (lists, scalars) replaces."""
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def diff_config(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            sub = f"{path}.{key}" if path else str(key)
            changes.extend(diff_config(before.get(key), after.get(key), sub))
        return changes
    return [] if before == after else [{"path": path, "before": before, "after": after}]


# Legacy flat fields used by the Agents page ↔ nested config.
def compat_to_patch(fields: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
    current = current or default_config()
    patch: dict[str, Any] = {}
    if "instructions" in fields:
        patch["instructions"] = fields["instructions"] or ""
    if "voice" in fields:
        patch.setdefault("voice", {})["voice"] = fields["voice"]
    if "model" in fields:
        patch.setdefault("voice", {})["live_model"] = fields["model"]
    if "temperature" in fields:
        patch.setdefault("llm", {})["temperature"] = fields["temperature"]
    language = fields.get("language")
    if language:
        supported = list(dict.fromkeys([language, *current["languages"]["supported"]]))
        patch["languages"] = {"default": language, "supported": supported}
    if "greeting" in fields:
        lang = language or current["languages"]["default"]
        patch["greetings"] = {lang: fields["greeting"] or ""}
    if "max_call_duration" in fields:
        patch["limits"] = {"max_call_seconds": fields["max_call_duration"]}
    if "fallback_phone" in fields:
        patch["handoff"] = {"phone": fields["fallback_phone"] or ""}
    hours = {k_new: fields[k_old] for k_old, k_new in (
        ("working_hours_start", "start"), ("working_hours_end", "end"), ("working_days", "days")) if k_old in fields}
    if hours:
        patch["hours"] = hours
    return patch


def config_to_compat(config: dict[str, Any]) -> dict[str, Any]:
    lang = config["languages"]["default"]
    return {
        "voice": config["voice"]["voice"],
        "model": config["voice"]["live_model"],
        "temperature": config["llm"]["temperature"],
        "instructions": config["instructions"],
        "language": lang,
        "greeting": config["greetings"].get(lang, ""),
        "max_call_duration": config["limits"]["max_call_seconds"],
        "fallback_phone": config["handoff"]["phone"],
        "working_hours_start": config["hours"]["start"],
        "working_hours_end": config["hours"]["end"],
        "working_days": config["hours"]["days"],
    }


# ── Queries ──────────────────────────────────────────────────────────
def get_version(db: Session, version_id: str | None) -> AgentVersion | None:
    return db.query(AgentVersion).filter(AgentVersion.id == version_id).first() if version_id else None


def current_config(db: Session, agent: Agent) -> dict[str, Any]:
    """What the agent looks like to an editor: the draft if one exists, else production, else the
    latest version (e.g. one still in testing or approval)."""
    version = (get_version(db, agent.draft_version_id) or get_version(db, agent.production_version_id)
               or db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id)
               .order_by(AgentVersion.number.desc()).first())
    return version.config if version else default_config()


def lifecycle(db: Session, agent: Agent) -> str:
    if agent.disabled_at is not None:
        return "disabled"
    if agent.production_version_id:
        return "production"
    latest = (db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id)
              .order_by(AgentVersion.number.desc()).first())
    return latest.status if latest else "draft"


# ── Mutations ────────────────────────────────────────────────────────
def _record_event(db: Session, agent: Agent, version: AgentVersion | None, action: str,
                  from_status: str | None, to_status: str | None, user: User | None, note: str | None) -> None:
    db.add(AgentLifecycleEvent(
        tenant_id=agent.tenant_id, agent_id=agent.id, version_id=version.id if version else None, action=action,
        from_status=from_status, to_status=to_status, user_id=user.id if user else None, note=note,
    ))


def _next_number(db: Session, agent_id: str) -> int:
    return (db.query(func.max(AgentVersion.number)).filter(AgentVersion.agent_id == agent_id).scalar() or 0) + 1


def create_agent(db: Session, user: User, *, name: str, description: str | None, tags: list[str],
                 config_patch: dict[str, Any], reason: str = "Agent created", source: str = "ui") -> Agent:
    config = validate_config(deep_merge(default_config(), config_patch))
    agent = Agent(tenant_id=user.tenant_id, name=name, description=description,
                  tags_csv=",".join(tags) or None, created_by=user.id)
    db.add(agent)
    db.flush()
    version = AgentVersion(tenant_id=agent.tenant_id, agent_id=agent.id, number=1, status="draft",
                           config=config, created_by=user.id)
    db.add(version)
    db.flush()
    agent.draft_version_id = version.id
    db.add(AgentChange(tenant_id=agent.tenant_id, agent_id=agent.id, version_id=version.id, user_id=user.id,
                       source=source, reason=reason, changes=diff_config(default_config(), config)))
    _record_event(db, agent, version, "create", None, "draft", user, reason)
    db.commit()
    db.refresh(agent)
    return agent


def ensure_draft(db: Session, agent: Agent, user: User) -> AgentVersion:
    """The agent's editable draft, created from production (or the latest version) when missing."""
    draft = get_version(db, agent.draft_version_id)
    if draft and draft.status == "draft":
        return draft
    base = get_version(db, agent.production_version_id) or (
        db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id).order_by(AgentVersion.number.desc()).first())
    draft = AgentVersion(
        tenant_id=agent.tenant_id, agent_id=agent.id, number=_next_number(db, agent.id), status="draft",
        config=copy.deepcopy(base.config) if base else default_config(),
        based_on_version_id=base.id if base else None, created_by=user.id,
    )
    db.add(draft)
    db.flush()
    agent.draft_version_id = draft.id
    _record_event(db, agent, draft, "new_draft", None, "draft", user,
                  f"Draft v{draft.number} created from v{base.number}" if base else None)
    return draft


def edit_draft(db: Session, agent: Agent, user: User, patch: dict[str, Any], *, reason: str,
               source: str = "ui") -> tuple[AgentVersion, list[dict[str, Any]]]:
    if agent.disabled_at is not None:
        raise AgentError("This agent is disabled. Enable it before editing.")
    draft = ensure_draft(db, agent, user)
    new_config = validate_config(deep_merge(draft.config, patch))
    changes = diff_config(draft.config, new_config)
    if changes:
        draft.config = new_config
        draft.updated_at = utcnow()
        db.add(AgentChange(tenant_id=agent.tenant_id, agent_id=agent.id, version_id=draft.id, user_id=user.id,
                           source=source, reason=reason, changes=changes))
    db.commit()
    db.refresh(draft)
    return draft, changes


def discard_draft(db: Session, agent: Agent, user: User) -> None:
    draft = get_version(db, agent.draft_version_id)
    if draft is None or draft.status != "draft":
        raise AgentError("There is no draft to discard.", status_code=404)
    if draft.number == 1 and not agent.production_version_id:
        raise AgentError("The first version of a new agent can't be discarded; delete the agent instead.")
    agent.draft_version_id = None
    draft.status = "rejected"
    _record_event(db, agent, draft, "discard", "draft", "rejected", user, None)
    db.commit()


def transition(db: Session, agent: Agent, version: AgentVersion, action: str, user: User,
               note: str | None = None) -> AgentVersion:
    if action not in TRANSITIONS:
        raise AgentError(f"Unknown action '{action}'", status_code=422)
    allowed_from, to_status, _ = TRANSITIONS[action]
    if version.agent_id != agent.id:
        raise AgentError("Version does not belong to this agent", status_code=404)
    if version.status not in allowed_from:
        raise AgentError(f"Can't {action} a version that is {version.status}.")
    if action in ("activate", "rollback") and agent.disabled_at is not None:
        raise AgentError("This agent is disabled. Enable it before activating a version.")
    if action == "rollback" and version.activated_at is None:
        raise AgentError("Only versions that were in production before can be rolled back to.")

    from_status = version.status
    now = utcnow()
    if action in ("activate", "rollback"):
        previous = get_version(db, agent.production_version_id)
        if previous is not None and previous.id != version.id:
            previous.status = "superseded"
            _record_event(db, agent, previous, "supersede", "production", "superseded", user, None)
        agent.production_version_id = version.id
        version.activated_at = now
    if action == "approve":
        version.approved_by = user.id
        version.approved_at = now
    if action == "submit" and agent.draft_version_id == version.id:
        agent.draft_version_id = None

    version.status = to_status
    version.updated_at = now
    _record_event(db, agent, version, action, from_status, to_status, user, note)
    db.commit()
    db.refresh(version)
    return version


def set_disabled(db: Session, agent: Agent, user: User, disabled: bool, note: str | None = None) -> None:
    if disabled == (agent.disabled_at is not None):
        return
    agent.disabled_at = utcnow() if disabled else None
    _record_event(db, agent, None, "disable" if disabled else "enable", None, None, user, note)
    db.commit()


@dataclass
class VersionDiff:
    from_number: int
    to_number: int
    changes: list[dict[str, Any]]


def compare(db: Session, agent: Agent, from_number: int, to_number: int) -> VersionDiff:
    rows = {v.number: v for v in db.query(AgentVersion).filter(
        AgentVersion.agent_id == agent.id, AgentVersion.number.in_([from_number, to_number])).all()}
    if from_number not in rows or to_number not in rows:
        raise AgentError("Version not found", status_code=404)
    return VersionDiff(from_number, to_number, diff_config(rows[from_number].config, rows[to_number].config))
