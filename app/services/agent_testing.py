"""Agent Studio: talk to any version of an agent, run its test cases, and gate evaluation on them.

Text tests use a Gemini text model with the version's instructions, greeting, language and the workspace's
knowledge base, so replies follow the same brief as the voice agent (the voice model itself runs in LiveKit;
the browser voice test covers that). A version can move to evaluation only when its latest test run passed
every case, as long as the agent has test cases.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent import Agent, AgentVersion
from app.models.agent_test import AgentTestCase, AgentTestRun

logger = logging.getLogger("agent-testing")

DEFAULT_TEXT_MODEL = "gemini-2.5-flash"
MAX_TURNS = 20
MAX_MESSAGE_CHARS = 2000


class AgentTestError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _client_kwargs(config: dict) -> dict[str, Any]:
    """Gemini through an API key or Vertex AI, the same way the voice runtime chooses."""
    if str(config.get("google_genai_use_vertexai") or "").lower() in ("1", "true", "yes", "on"):
        kwargs: dict[str, Any] = {"vertexai": True, "location": str(config.get("google_cloud_location") or "us-central1")}
        if config.get("google_cloud_project"):
            kwargs["project"] = str(config["google_cloud_project"])
        return kwargs
    api_key = str(config.get("google_api_key") or "").strip()
    if not api_key:
        raise AgentTestError("Set a Google API key (or Vertex AI) in Configuration to test agents.", 503)
    return {"api_key": api_key}


def generate(client_kwargs: dict[str, Any], model: str, system: str, turns: list[dict[str, str]]) -> str:
    """One model reply. Tests replace this."""
    from google import genai
    from google.genai import types
    client = genai.Client(**client_kwargs)
    contents = [types.Content(role="user" if t["role"] == "caller" else "model", parts=[types.Part(text=t["text"])])
                for t in turns]
    response = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.4, max_output_tokens=400))
    return str(response.text or "").strip()


def system_prompt(version: AgentVersion, tenant_id: str, latest_caller_text: str, config: dict) -> str:
    cfg = version.config or {}
    languages = cfg.get("languages") or {}
    lang = languages.get("default") or "en"
    greeting = (cfg.get("greetings") or {}).get(lang) or ""
    parts = [
        str(cfg.get("instructions") or "You are a helpful phone assistant for this business."),
        "You are speaking on a phone call; keep replies short and natural, one or two sentences.",
        f"Reply in the caller's language; the default is '{lang}'"
        + (f" (also supported: {', '.join(languages.get('supported') or [])})." if languages.get("supported") else "."),
    ]
    if greeting:
        parts.append(f"You opened the call with: \"{greeting}\"")
    try:
        import kb
        grounding = kb.search_for_agent(latest_caller_text, config=config, tenant_id=tenant_id)
        if grounding and grounding.get("grounding_text"):
            parts.append("Business knowledge for this question:\n" + grounding["grounding_text"])
    except Exception as exc:  # the knowledge base is optional for a test reply
        logger.warning("[AGENT-TEST] Knowledge base lookup failed: %s", exc)
    return "\n\n".join(parts)


def reply(version: AgentVersion, tenant_id: str, turns: list[dict[str, str]], config: dict) -> str:
    """The agent's next reply to a conversation of {"role": "caller"|"agent", "text"} turns."""
    if not turns or turns[-1]["role"] != "caller":
        raise AgentTestError("The conversation must end with something the caller says.", 422)
    if len(turns) > MAX_TURNS * 2:
        raise AgentTestError(f"Keep test conversations under {MAX_TURNS} caller turns.", 422)
    for t in turns:
        if t["role"] not in ("caller", "agent") or not str(t.get("text") or "").strip():
            raise AgentTestError("Each turn needs a role (caller or agent) and some text.", 422)
        if len(t["text"]) > MAX_MESSAGE_CHARS:
            raise AgentTestError(f"Keep each message under {MAX_MESSAGE_CHARS} characters.", 422)
    kwargs = _client_kwargs(config)
    model = str(config.get("gemini_text_model") or DEFAULT_TEXT_MODEL)
    try:
        text = generate(kwargs, model, system_prompt(version, tenant_id, turns[-1]["text"], config), turns)
    except AgentTestError:
        raise
    except Exception as exc:
        raise AgentTestError(f"The model didn't answer: {exc}", 502) from exc
    return text or "(no reply)"


# Languages a test can require: the ones whose script tells them apart (see call_language).
TESTABLE_LANGUAGES = ("en", "te", "hi", "ta", "kn", "ml")
# English replies may name a place or two in another script; Indian-language replies usually carry English
# words ("appointment", brand names), so a clear share of their own script is enough; a reply in English or
# another script scores about 0.
LANGUAGE_SHARE = {"en": 0.8}
DEFAULT_LANGUAGE_SHARE = 0.35


def check_case(case: AgentTestCase, replies: list[str]) -> dict[str, Any]:
    from app.services import call_language
    said = "\n".join(replies).lower()
    missing = [p for p in (case.must_include or []) if p.lower() not in said]
    forbidden = [p for p in (case.must_not_include or []) if p.lower() in said]
    wrong_language: list[int] = []
    expected = getattr(case, "expected_language", None)
    if expected:
        needed = LANGUAGE_SHARE.get(expected, DEFAULT_LANGUAGE_SHARE)
        wrong_language = [i + 1 for i, r in enumerate(replies) if call_language.share(r, expected) < needed]
    return {"passed": not missing and not forbidden and not wrong_language, "missing": missing, "forbidden": forbidden,
            "expected_language": expected, "wrong_language_replies": wrong_language}


def run_tests(db: Session, agent: Agent, version: AgentVersion, user_id: str | None, config: dict) -> AgentTestRun:
    cases = db.query(AgentTestCase).filter(AgentTestCase.agent_id == agent.id).order_by(AgentTestCase.created_at).all()
    if not cases:
        raise AgentTestError("Add at least one test case first.", 409)
    results = []
    for case in cases:
        turns: list[dict[str, str]] = []
        replies: list[str] = []
        error = None
        try:
            for said in case.caller_turns:
                turns.append({"role": "caller", "text": str(said)})
                answer = reply(version, agent.tenant_id, turns, config)
                turns.append({"role": "agent", "text": answer})
                replies.append(answer)
            verdict = check_case(case, replies)
        except AgentTestError as exc:
            error, verdict = str(exc), {"passed": False, "missing": [], "forbidden": []}
        results.append({"case_id": case.id, "name": case.name, "transcript": turns, "error": error, **verdict})
    run = AgentTestRun(tenant_id=agent.tenant_id, agent_id=agent.id, version_id=version.id,
                       passed=sum(1 for r in results if r["passed"]), total=len(results), results=results,
                       created_by=user_id, created_at=_now())
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def latest_run(db: Session, version: AgentVersion) -> AgentTestRun | None:
    return db.query(AgentTestRun).filter(AgentTestRun.version_id == version.id).order_by(AgentTestRun.created_at.desc()).first()


def evaluation_blocker(db: Session, agent: Agent, version: AgentVersion) -> str | None:
    """Why the version can't go to evaluation yet, or None. Agents without test cases aren't gated."""
    cases = db.query(AgentTestCase).filter(AgentTestCase.agent_id == agent.id).count()
    if not cases:
        return None
    run = latest_run(db, version)
    if run is None:
        return f"Run this version's {cases} test case{'s' if cases != 1 else ''} before sending it to evaluation."
    if run.total < cases:
        return "Test cases were added since the last run. Run the tests again."
    if run.passed < run.total:
        return f"The last test run passed {run.passed} of {run.total} cases. Fix the version or the tests, then run them again."
    return None


VOICE_TEST_TTL_MINUTES = 30


async def start_voice_test(agent: Agent, version: AgentVersion, user_id: str, user_name: str, config: dict) -> dict:
    """A sandbox room where the tester talks to this version through the browser microphone. No phone line is
    involved, and the voice worker saves no call log, booking or campaign result for test sessions."""
    import json
    import secrets
    from datetime import timedelta

    from livekit import api

    from outbound_calls import DEFAULT_AGENT_NAME, get_livekit_settings
    settings = get_livekit_settings(config)
    if not (settings["url"] and settings["api_key"] and settings["api_secret"]):
        raise AgentTestError("LiveKit is not configured, so voice tests can't start.", 503)
    room = f"test-{secrets.token_hex(8)}"
    lk = api.LiveKitAPI(url=settings["url"], api_key=settings["api_key"], api_secret=settings["api_secret"])
    try:
        await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
            agent_name=DEFAULT_AGENT_NAME, room=room,
            metadata=json.dumps({"tenant_id": agent.tenant_id, "agent_id": agent.id, "test_version": version.number,
                                 "direction": "test"})))
    except api.TwirpError as exc:
        raise AgentTestError(f"LiveKit couldn't start the test: {exc.message}", 502) from exc
    finally:
        await lk.aclose()
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True, can_publish_data=False)
    token = (api.AccessToken(settings["api_key"], settings["api_secret"]).with_identity(f"tester-{user_id}")
             .with_name(user_name).with_grants(grants).with_ttl(timedelta(minutes=VOICE_TEST_TTL_MINUTES)).to_jwt())
    return {"url": settings["url"], "token": token, "room": room, "version": version.number}

