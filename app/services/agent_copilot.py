"""Agent Copilot: describe a change in plain words, see exactly what would change, then apply it to the draft.

The model only proposes. Its patch is limited to the fields below, validated like any other edit, and shown as a
diff first; applying it goes through the normal draft (and so still needs submit → evaluate → approve → activate).
Model names, knowledge sources, tools and workflows stay out of its reach.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services import agents as svc
from app.services.agent_testing import DEFAULT_TEXT_MODEL, AgentTestError, _client_kwargs

logger = logging.getLogger("agent-copilot")

MAX_REQUEST_CHARS = 1000
# Top-level key -> the nested keys the copilot may set (None: the whole value).
EDITABLE: dict[str, set[str] | None] = {
    "instructions": None,
    "greetings": None,
    "languages": {"supported", "default", "auto_detect"},
    "llm": {"temperature"},
    "voice": {"voice"},
    "limits": {"max_call_seconds"},
    "hours": {"timezone", "days", "start", "end"},
    "handoff": {"phone"},
}
VOICES = ["Puck", "Charon", "Kore", "Fenrir", "Aoede", "Leda"]  # the ones the Agents page offers


class CopilotError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def editable_view(config: dict[str, Any]) -> dict[str, Any]:
    view: dict[str, Any] = {}
    for key, sub in EDITABLE.items():
        value = config.get(key)
        view[key] = value if sub is None or not isinstance(value, dict) else {k: v for k, v in value.items() if k in sub}
    return view


def restrict(patch: Any) -> tuple[dict[str, Any], list[str]]:
    """Keep only what the copilot may change. Returns the kept patch and the paths it dropped."""
    if not isinstance(patch, dict):
        return {}, ["(not an object)"]
    kept: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in patch.items():
        if key not in EDITABLE:
            dropped.append(str(key))
            continue
        sub = EDITABLE[key]
        if sub is None:
            kept[key] = value
        elif isinstance(value, dict):
            inner = {k: v for k, v in value.items() if k in sub}
            dropped.extend(f"{key}.{k}" for k in value if k not in sub)
            if inner:
                kept[key] = inner
        else:
            dropped.append(str(key))
    return kept, dropped


def prompt(current: dict[str, Any], request: str) -> str:
    return "\n".join([
        "You edit the configuration of a phone voice agent. Apply the user's request to the configuration and reply "
        "with JSON only: {\"summary\": \"<one or two sentences on what you changed>\", \"patch\": {...}}.",
        "The patch holds only the keys that change. Nested objects merge; lists and strings replace, so for "
        "`instructions` return the complete new text, keeping everything the request doesn't touch.",
        "Fields you may change:",
        "- instructions: the agent's brief (plain text, under 20000 characters)",
        "- greetings: opening line per language code, e.g. {\"hi\": \"Namaste…\"} (under 500 characters each)",
        "- languages: {supported: [codes], default: code, auto_detect: bool}; codes: en te hi ta kn ml ar es fr de pt ja ko zh",
        "- llm.temperature: 0 to 2",
        f"- voice.voice: one of {', '.join(VOICES)}",
        "- limits.max_call_seconds: 30 to 7200",
        "- hours: {timezone, days: [Mon..Sun], start: \"HH:MM\", end: \"HH:MM\"}",
        "- handoff.phone: number to transfer callers to, with country code",
        "If the request asks for anything else (knowledge, tools, models, workflows, prices you weren't given), don't "
        "invent it; leave it out of the patch and say so in the summary. If nothing should change, return an empty patch.",
        "",
        "Current configuration:",
        json.dumps(current, ensure_ascii=False, indent=1),
        "",
        "Request:",
        request,
    ])


def generate_json(client_kwargs: dict[str, Any], model: str, text: str) -> str:
    """One JSON answer from the model. Tests replace this."""
    from google import genai
    from google.genai import types
    client = genai.Client(**client_kwargs)
    response = client.models.generate_content(
        model=model, contents=text,
        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=8192, response_mime_type="application/json"))
    return str(response.text or "")


def propose(current_config: dict[str, Any], request: str, config: dict) -> dict[str, Any]:
    request = str(request or "").strip()
    if len(request) < 3:
        raise CopilotError("Describe the change you want.", 422)
    if len(request) > MAX_REQUEST_CHARS:
        raise CopilotError(f"Keep the request under {MAX_REQUEST_CHARS} characters.", 422)
    try:
        kwargs = _client_kwargs(config)
    except AgentTestError as exc:
        raise CopilotError(str(exc), exc.status_code) from exc
    model = str(config.get("gemini_text_model") or DEFAULT_TEXT_MODEL)
    try:
        raw = generate_json(kwargs, model, prompt(editable_view(current_config), request))
    except Exception as exc:
        logger.warning("[COPILOT] Model call failed: %s", exc)
        raise CopilotError(f"The model didn't answer: {exc}", 502) from exc
    try:
        answer = json.loads(raw)
    except ValueError as exc:
        raise CopilotError("The model's answer wasn't usable. Try rephrasing the request.", 502) from exc
    if not isinstance(answer, dict):
        raise CopilotError("The model's answer wasn't usable. Try rephrasing the request.", 502)
    return check(current_config, answer.get("patch") or {}, str(answer.get("summary") or "").strip()[:1000])


def check(current_config: dict[str, Any], patch: Any, summary: str = "") -> dict[str, Any]:
    """Restrict and validate a patch against the current config; returns the preview."""
    kept, dropped = restrict(patch)
    try:
        after = svc.validate_config(svc.deep_merge(current_config, kept))
    except svc.AgentError as exc:
        raise CopilotError(f"The suggested change isn't valid: {exc}. Try rephrasing the request.", 422) from exc
    return {"summary": summary, "patch": kept, "changes": svc.diff_config(current_config, after), "ignored": dropped}
