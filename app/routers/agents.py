from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.core.permissions import at_least
from app.models.agent import Agent, AgentChange, AgentLifecycleEvent, AgentPhoneNumber, AgentVersion
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    ChangeOut,
    DraftPatchIn,
    DraftPatchOut,
    LifecycleEventOut,
    TransitionIn,
    VersionDiffOut,
    VersionOut,
)
from app.services import agents as svc
from app.services import audit
from app.schemas.common import UTCDateTime

router = APIRouter(prefix="/api/agents", tags=["Agents"])

require_builder = RoleChecker(["Manager"])
require_admin = RoleChecker(["Admin"])

_COMPAT_FIELDS = set(AgentCreate.model_fields) - {"name", "description", "tags"}


def _raise(exc: svc.AgentError):
    raise HTTPException(status_code=exc.status_code, detail=str(exc))


def _get_agent(db: Session, agent_id: str, user: User) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.tenant_id == user.tenant_id).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _get_version(db: Session, agent: Agent, number: int) -> AgentVersion:
    version = db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id, AgentVersion.number == number).first()
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version {number} not found")
    return version


def _agent_out(db: Session, agent: Agent) -> AgentOut:
    production = svc.get_version(db, agent.production_version_id)
    draft = svc.get_version(db, agent.draft_version_id)
    return AgentOut(
        id=agent.id, name=agent.name, description=agent.description,
        tags=[t.strip() for t in (agent.tags_csv or "").split(",") if t.strip()],
        status=agent.status, lifecycle=svc.lifecycle(db, agent),
        production_version=production.number if production else None,
        draft_version=draft.number if draft and draft.status == "draft" else None,
        calls_today=agent.calls_today, calls_total=agent.calls_total, avg_duration=agent.avg_duration,
        success_rate=agent.success_rate, last_active=agent.last_active,
        **svc.config_to_compat(svc.current_config(db, agent)),
    )


def _version_out(version: AgentVersion) -> VersionOut:
    return VersionOut.model_validate(version, from_attributes=True)


@router.get("", response_model=List[AgentOut])
def list_agents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    agents = db.query(Agent).filter(Agent.tenant_id == current_user.tenant_id).order_by(Agent.name).all()
    return [_agent_out(db, a) for a in agents]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(require_builder)):
    from app.services import plan_limits
    try:
        plan_limits.check_new_agent(db, current_user.tenant_id)
    except plan_limits.LimitReached as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    fields = payload.model_dump(include=_COMPAT_FIELDS, exclude_none=True)
    try:
        agent = svc.create_agent(db, current_user, name=payload.name.strip(), description=payload.description,
                                 tags=payload.tags, config_patch=svc.compat_to_patch(fields))
    except svc.AgentError as exc:
        _raise(exc)
    audit.record(db, action="agent_created", entity="Agent", entity_id=agent.id, tenant_id=agent.tenant_id,
                 user_id=current_user.id, request=request)
    return _agent_out(db, agent)


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _agent_out(db, _get_agent(db, agent_id, current_user))


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: str, payload: AgentUpdate, db: Session = Depends(get_db),
                 current_user: User = Depends(require_builder)):
    """Identity fields change directly; configuration fields go to the draft version."""
    agent = _get_agent(db, agent_id, current_user)
    if payload.name is not None:
        agent.name = payload.name.strip()
    if payload.description is not None:
        agent.description = payload.description
    if payload.tags is not None:
        agent.tags_csv = ",".join(payload.tags) or None
    fields = payload.model_dump(include=_COMPAT_FIELDS, exclude_unset=True)
    if fields:
        try:
            svc.edit_draft(db, agent, current_user, svc.compat_to_patch(fields, svc.current_config(db, agent)),
                           reason=payload.reason or "Edited in agent settings")
        except svc.AgentError as exc:
            _raise(exc)
    else:
        db.commit()
    db.refresh(agent)
    return _agent_out(db, agent)


@router.delete("/{agent_id}")
def delete_agent(agent_id: str, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    agent = _get_agent(db, agent_id, current_user)
    # Clear the circular pointers first so versions can be removed with the agent.
    agent.production_version_id = None
    agent.draft_version_id = None
    db.flush()
    db.query(AgentChange).filter(AgentChange.agent_id == agent.id).delete()
    db.query(AgentLifecycleEvent).filter(AgentLifecycleEvent.agent_id == agent.id).delete()
    db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id).delete()
    db.query(AgentPhoneNumber).filter(AgentPhoneNumber.agent_id == agent.id).delete()
    db.delete(agent)
    db.commit()
    audit.record(db, action="agent_deleted", entity="Agent", entity_id=agent_id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"name": agent.name}, request=request)
    return {"status": "ok", "success": True}


@router.get("/{agent_id}/versions", response_model=List[VersionOut])
def list_versions(agent_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    agent = _get_agent(db, agent_id, current_user)
    rows = db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id).order_by(AgentVersion.number.desc()).all()
    return [_version_out(v) for v in rows]


@router.get("/{agent_id}/versions/{number}", response_model=VersionOut)
def get_version(agent_id: str, number: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    return _version_out(_get_version(db, _get_agent(db, agent_id, current_user), number))


@router.patch("/{agent_id}/draft", response_model=DraftPatchOut)
def patch_draft(agent_id: str, payload: DraftPatchIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_builder)):
    """Apply a partial config change to the draft (created from production if needed), with a reason."""
    agent = _get_agent(db, agent_id, current_user)
    try:
        version, changes = svc.edit_draft(db, agent, current_user, payload.patch, reason=payload.reason)
    except svc.AgentError as exc:
        _raise(exc)
    return DraftPatchOut(version=_version_out(version), changes=changes)


@router.delete("/{agent_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def discard_draft(agent_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_builder)):
    try:
        svc.discard_draft(db, _get_agent(db, agent_id, current_user), current_user)
    except svc.AgentError as exc:
        _raise(exc)


@router.post("/{agent_id}/versions/{number}/{action}", response_model=VersionOut)
def version_action(agent_id: str, number: int, action: str, request: Request, payload: TransitionIn | None = None,
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Lifecycle: submit → evaluate → approve → activate; reject; rollback to an earlier production version."""
    if action not in svc.TRANSITIONS:
        raise HTTPException(status_code=404, detail=f"Unknown action '{action}'")
    minimum_role = svc.TRANSITIONS[action][2]
    if not at_least(current_user.role, minimum_role):
        raise HTTPException(status_code=403, detail=f"This action requires the {minimum_role} role or higher.")
    agent = _get_agent(db, agent_id, current_user)
    version = _get_version(db, agent, number)
    try:
        version = svc.transition(db, agent, version, action, current_user, payload.note if payload else None)
    except svc.AgentError as exc:
        _raise(exc)
    if action in ("activate", "rollback"):
        audit.record(db, action=f"agent_version_{action}", entity="Agent", entity_id=agent.id,
                     tenant_id=agent.tenant_id, user_id=current_user.id, details={"version": number}, request=request)
    return _version_out(version)


@router.post("/{agent_id}/disable", response_model=AgentOut)
def disable_agent(agent_id: str, payload: TransitionIn | None = None, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    agent = _get_agent(db, agent_id, current_user)
    svc.set_disabled(db, agent, current_user, True, payload.note if payload else None)
    return _agent_out(db, agent)


@router.post("/{agent_id}/enable", response_model=AgentOut)
def enable_agent(agent_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    agent = _get_agent(db, agent_id, current_user)
    svc.set_disabled(db, agent, current_user, False)
    return _agent_out(db, agent)


@router.get("/{agent_id}/compare", response_model=VersionDiffOut)
def compare_versions(agent_id: str, from_version: int = Query(alias="from"), to_version: int = Query(alias="to"),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        diff = svc.compare(db, _get_agent(db, agent_id, current_user), from_version, to_version)
    except svc.AgentError as exc:
        _raise(exc)
    return VersionDiffOut(from_version=diff.from_number, to_version=diff.to_number, changes=diff.changes)


def _numbers(db: Session, agent: Agent) -> dict[str, int]:
    return dict(db.query(AgentVersion.id, AgentVersion.number).filter(AgentVersion.agent_id == agent.id).all())


def _names(db: Session, user_ids: set[str]) -> dict[str, str]:
    ids = [i for i in user_ids if i]
    return dict(db.query(User.id, User.name).filter(User.id.in_(ids)).all()) if ids else {}


@router.get("/{agent_id}/changes", response_model=List[ChangeOut])
def list_changes(agent_id: str, limit: int = Query(default=100, le=500), db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    agent = _get_agent(db, agent_id, current_user)
    rows = (db.query(AgentChange).filter(AgentChange.agent_id == agent.id)
            .order_by(AgentChange.created_at.desc()).limit(limit).all())
    numbers, names = _numbers(db, agent), _names(db, {r.user_id for r in rows})
    return [ChangeOut(id=r.id, version_number=numbers.get(r.version_id, 0), user_id=r.user_id,
                      user_name=names.get(r.user_id), source=r.source, reason=r.reason, changes=r.changes,
                      created_at=r.created_at) for r in rows]


@router.get("/{agent_id}/events", response_model=List[LifecycleEventOut])
def list_events(agent_id: str, limit: int = Query(default=100, le=500), db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    agent = _get_agent(db, agent_id, current_user)
    rows = (db.query(AgentLifecycleEvent).filter(AgentLifecycleEvent.agent_id == agent.id)
            .order_by(AgentLifecycleEvent.created_at.desc()).limit(limit).all())
    numbers, names = _numbers(db, agent), _names(db, {r.user_id for r in rows})
    return [LifecycleEventOut(id=r.id, version_number=numbers.get(r.version_id), action=r.action,
                              from_status=r.from_status, to_status=r.to_status, user_name=names.get(r.user_id),
                              note=r.note, created_at=r.created_at) for r in rows]


class PhoneNumberIn(BaseModel):
    phone_number: str


class PhoneNumberOut(BaseModel):
    id: str
    phone_number: str
    created_at: UTCDateTime


@router.get("/{agent_id}/numbers", response_model=List[PhoneNumberOut])
def list_numbers(agent_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Business numbers this agent answers."""
    agent = _get_agent(db, agent_id, current_user)
    return db.query(AgentPhoneNumber).filter(AgentPhoneNumber.agent_id == agent.id).order_by(AgentPhoneNumber.created_at).all()


@router.post("/{agent_id}/numbers", response_model=PhoneNumberOut, status_code=status.HTTP_201_CREATED)
def add_number(agent_id: str, payload: PhoneNumberIn, request: Request, db: Session = Depends(get_db),
               current_user: User = Depends(require_admin)):
    """Route calls to this number to this agent. The number must also point at your LiveKit SIP trunk."""
    from app.services.agent_runtime import canonical_number
    agent = _get_agent(db, agent_id, current_user)
    number = canonical_number(payload.phone_number)
    if not number:
        raise HTTPException(status_code=422, detail="Enter the number with its country code, e.g. +914012345678")
    existing = db.query(AgentPhoneNumber).filter(AgentPhoneNumber.phone_number == number).first()
    if existing:
        # Don't reveal which workspace holds it.
        same = existing.tenant_id == current_user.tenant_id
        raise HTTPException(status_code=409, detail="This number is already connected to "
                            + ("another of your agents." if same and existing.agent_id != agent.id else
                               "this agent." if same else "an agent. Contact support if it's yours."))
    row = AgentPhoneNumber(tenant_id=current_user.tenant_id, agent_id=agent.id, phone_number=number)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # On Postgres, row-level security hides other workspaces' numbers from the check above,
        # so a number held elsewhere only shows up as the unique constraint.
        db.rollback()
        raise HTTPException(status_code=409, detail="This number is already connected to an agent. "
                            "Contact support if it's yours.")
    db.refresh(row)
    audit.record(db, action="agent_number_added", entity="Agent", entity_id=agent.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"phone_number": number}, request=request)
    return row


@router.delete("/{agent_id}/numbers/{number_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_number(agent_id: str, number_id: str, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    agent = _get_agent(db, agent_id, current_user)
    row = db.query(AgentPhoneNumber).filter(AgentPhoneNumber.id == number_id, AgentPhoneNumber.agent_id == agent.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Number not found")
    number = row.phone_number
    db.delete(row)
    db.commit()
    audit.record(db, action="agent_number_removed", entity="Agent", entity_id=agent.id, tenant_id=current_user.tenant_id,
                 user_id=current_user.id, details={"phone_number": number}, request=request)


# ── Agent Studio: test a version by text or voice, and its regression tests ─────────

class TestTurnIn(BaseModel):
    role: str  # caller | agent
    text: str


class TestChatIn(BaseModel):
    turns: List[TestTurnIn]


class TestChatOut(BaseModel):
    reply: str


class TestCaseIn(BaseModel):
    name: str
    caller_turns: List[str]
    must_include: List[str] = []
    must_not_include: List[str] = []
    expected_language: Optional[Literal["en", "te", "hi", "ta", "kn", "ml"]] = None


class TestCaseOut(TestCaseIn):
    id: str
    created_at: UTCDateTime

    class Config:
        from_attributes = True


class TestRunOut(BaseModel):
    id: str
    version_number: int
    passed: int
    total: int
    results: list
    created_at: UTCDateTime


class VoiceTestOut(BaseModel):
    url: str
    token: str
    room: str
    version: int


def _studio_error(exc) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc))


def _clean_list(items: List[str], limit: int, what: str) -> list[str]:
    cleaned = [i.strip() for i in items if i and i.strip()]
    if len(cleaned) > limit or any(len(i) > 500 for i in cleaned):
        raise HTTPException(status_code=422, detail=f"Use at most {limit} {what}, each under 500 characters.")
    return cleaned


@router.get("/{agent_id}/tests", response_model=List[TestCaseOut])
def list_test_cases(agent_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.agent_test import AgentTestCase
    agent = _get_agent(db, agent_id, current_user)
    return db.query(AgentTestCase).filter(AgentTestCase.agent_id == agent.id).order_by(AgentTestCase.created_at).all()


@router.post("/{agent_id}/tests", response_model=TestCaseOut, status_code=status.HTTP_201_CREATED)
def create_test_case(agent_id: str, payload: TestCaseIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_builder)):
    """A scripted conversation this agent must pass before a version can go to evaluation."""
    from datetime import datetime, timezone

    from app.models.agent_test import AgentTestCase
    agent = _get_agent(db, agent_id, current_user)
    turns = _clean_list(payload.caller_turns, 10, "caller messages")
    if not payload.name.strip() or not turns:
        raise HTTPException(status_code=422, detail="Give the test a name and at least one thing the caller says.")
    must, must_not = _clean_list(payload.must_include, 10, "required phrases"), _clean_list(payload.must_not_include, 10, "forbidden phrases")
    if not must and not must_not and not payload.expected_language:
        raise HTTPException(status_code=422, detail="Add a phrase the replies must or must not contain, or the language they must be in.")
    case = AgentTestCase(tenant_id=agent.tenant_id, agent_id=agent.id, name=payload.name.strip()[:150], caller_turns=turns,
                         must_include=must, must_not_include=must_not, expected_language=payload.expected_language,
                         created_by=current_user.id,
                         created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.delete("/{agent_id}/tests/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_case(agent_id: str, case_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_builder)):
    from app.models.agent_test import AgentTestCase
    agent = _get_agent(db, agent_id, current_user)
    deleted = db.query(AgentTestCase).filter(AgentTestCase.id == case_id, AgentTestCase.agent_id == agent.id).delete()
    db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Test case not found")


@router.post("/{agent_id}/versions/{number}/test/chat", response_model=TestChatOut)
def test_chat(agent_id: str, number: int, payload: TestChatIn, db: Session = Depends(get_db),
              current_user: User = Depends(require_builder)):
    """The version's next reply to a typed conversation. Nothing is saved or sent to anyone."""
    from app.core.runtime_config import load_runtime_config
    from app.services import agent_testing
    agent = _get_agent(db, agent_id, current_user)
    version = _get_version(db, agent, number)
    try:
        return TestChatOut(reply=agent_testing.reply(version, agent.tenant_id, [t.model_dump() for t in payload.turns],
                                                     load_runtime_config()))
    except agent_testing.AgentTestError as exc:
        _studio_error(exc)


@router.post("/{agent_id}/versions/{number}/test/run", response_model=TestRunOut)
def run_version_tests(agent_id: str, number: int, request: Request, db: Session = Depends(get_db),
                      current_user: User = Depends(require_builder)):
    """Run every test case against this version and record the result."""
    from app.core.runtime_config import load_runtime_config
    from app.services import agent_testing
    agent = _get_agent(db, agent_id, current_user)
    version = _get_version(db, agent, number)
    try:
        run = agent_testing.run_tests(db, agent, version, current_user.id, load_runtime_config())
    except agent_testing.AgentTestError as exc:
        _studio_error(exc)
    audit.record(db, action="agent_tests_run", entity="Agent", entity_id=agent.id, tenant_id=agent.tenant_id,
                 user_id=current_user.id, details={"version": number, "passed": run.passed, "total": run.total}, request=request)
    return TestRunOut(id=run.id, version_number=number, passed=run.passed, total=run.total, results=run.results,
                      created_at=run.created_at)


@router.get("/{agent_id}/versions/{number}/test/runs", response_model=List[TestRunOut])
def list_version_test_runs(agent_id: str, number: int, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    from app.models.agent_test import AgentTestRun
    agent = _get_agent(db, agent_id, current_user)
    version = _get_version(db, agent, number)
    runs = db.query(AgentTestRun).filter(AgentTestRun.version_id == version.id).order_by(AgentTestRun.created_at.desc()).limit(10).all()
    return [TestRunOut(id=r.id, version_number=number, passed=r.passed, total=r.total, results=r.results, created_at=r.created_at)
            for r in runs]


@router.post("/{agent_id}/versions/{number}/test/voice", response_model=VoiceTestOut)
async def voice_test(agent_id: str, number: int, db: Session = Depends(get_db), current_user: User = Depends(require_builder)):
    """Talk to this version through the browser microphone in a sandbox room; no phone is dialled."""
    from app.core.runtime_config import load_runtime_config
    from app.services import agent_testing
    agent = _get_agent(db, agent_id, current_user)
    version = _get_version(db, agent, number)
    try:
        return await agent_testing.start_voice_test(agent, version, current_user.id, current_user.name or current_user.email,
                                                    load_runtime_config())
    except agent_testing.AgentTestError as exc:
        _studio_error(exc)


# --- Copilot ---------------------------------------------------------------------------------------

class CopilotIn(BaseModel):
    request: str = Field(min_length=3, max_length=1000)


class ConfigChangeOut(BaseModel):
    path: str
    before: Any = None
    after: Any = None


class CopilotProposalOut(BaseModel):
    summary: str
    patch: Dict[str, Any]
    changes: List[ConfigChangeOut]
    ignored: List[str]


class CopilotApplyIn(BaseModel):
    request: str = Field(min_length=3, max_length=1000)
    patch: Dict[str, Any]


@router.post("/{agent_id}/copilot", response_model=CopilotProposalOut)
def copilot_propose(agent_id: str, payload: CopilotIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_builder)):
    """Turn a plain-language request into a proposed change to the agent's current configuration.
    Nothing is saved; apply it with /copilot/apply."""
    from app.core.runtime_config import load_runtime_config
    from app.services import agent_copilot
    agent = _get_agent(db, agent_id, current_user)
    try:
        return agent_copilot.propose(svc.current_config(db, agent), payload.request, load_runtime_config())
    except agent_copilot.CopilotError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/{agent_id}/copilot/apply", response_model=DraftPatchOut)
def copilot_apply(agent_id: str, payload: CopilotApplyIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_builder)):
    """Apply a copilot proposal to the draft, logged as a copilot change with the request as the reason."""
    from app.services import agent_copilot
    agent = _get_agent(db, agent_id, current_user)
    try:
        preview = agent_copilot.check(svc.current_config(db, agent), payload.patch)
    except agent_copilot.CopilotError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    if not preview["changes"]:
        raise HTTPException(status_code=409, detail="That proposal doesn't change anything any more.")
    try:
        version, changes = svc.edit_draft(db, agent, current_user, preview["patch"], reason=f"Copilot: {payload.request}"[:500],
                                          source="copilot")
    except svc.AgentError as exc:
        _raise(exc)
    return DraftPatchOut(version=_version_out(version), changes=changes)
