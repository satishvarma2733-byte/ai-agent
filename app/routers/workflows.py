import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.workflow import Workflow, WorkflowLog
from app.schemas.workflow import WorkflowOut, WorkflowCreate, WorkflowLogOut
from app.services.appointment_reminders import DEFAULT_REMINDER_MINUTES, MAX_REMINDER_MINUTES, MIN_REMINDER_MINUTES
from app.services.workflow_engine import TRIGGERS, normalize_trigger
from app.core.auth_deps import get_current_user, RoleChecker
from app.models.user import User

router = APIRouter(prefix="/api/crm/workflows", tags=["Automation Workflows"])


def _trigger(name: str) -> str:
    trigger = normalize_trigger(name)
    if trigger not in TRIGGERS:
        raise HTTPException(status_code=422, detail=f"Unsupported trigger '{name}'. Use one of: {', '.join(TRIGGERS)}.")
    return trigger


def _trigger_config(trigger: str, config: dict | None) -> str | None:
    """Only reminders take settings: how long before the appointment they fire."""
    if trigger != "appointment_reminder":
        return None
    raw = (config or {}).get("minutes_before", DEFAULT_REMINDER_MINUTES)
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="minutes_before must be a whole number of minutes.")
    if not MIN_REMINDER_MINUTES <= minutes <= MAX_REMINDER_MINUTES:
        raise HTTPException(status_code=422, detail=f"Reminders can be sent {MIN_REMINDER_MINUTES} minutes to "
                                                    f"{MAX_REMINDER_MINUTES // 1440} days before the appointment.")
    return json.dumps({"minutes_before": minutes})


def _out(wf: Workflow, actions: list) -> WorkflowOut:
    return WorkflowOut(id=wf.id, name=wf.name, trigger_event=normalize_trigger(wf.trigger_event), is_active=wf.is_active,
                       trigger_config=json.loads(wf.trigger_config) if wf.trigger_config else None,
                       actions=actions, created_at=wf.created_at)

@router.get("", response_model=List[WorkflowOut])
def list_workflows(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List automation configurations for the active tenant."""
    rows = db.query(Workflow).filter(
        Workflow.tenant_id == current_user.tenant_id
    ).order_by(Workflow.created_at.desc()).all()
    
    results = []
    for row in rows:
        try:
            actions_list = json.loads(row.actions_json)
        except Exception:
            actions_list = []
            
        results.append(_out(row, actions_list))
    return results

@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Manager"]))
):
    """Add a new automated pipeline sequence (Admins/Managers only)."""
    actions = [action.model_dump() for action in payload.actions]
    actions_json = json.dumps(actions)
    
    trigger = _trigger(payload.trigger_event)
    wf = Workflow(
        name=payload.name,
        trigger_event=trigger,
        trigger_config=_trigger_config(trigger, payload.trigger_config),
        is_active=payload.is_active,
        actions_json=actions_json,
        tenant_id=current_user.tenant_id
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    
    return _out(wf, actions)

@router.put("/{id}", response_model=WorkflowOut)
def update_workflow(
    id: str,
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Manager"]))
):
    """Update workflow settings (Admins/Managers only)."""
    wf = db.query(Workflow).filter(
        Workflow.id == id,
        Workflow.tenant_id == current_user.tenant_id
    ).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    wf.name = payload.name
    wf.trigger_event = _trigger(payload.trigger_event)
    wf.trigger_config = _trigger_config(wf.trigger_event, payload.trigger_config)
    wf.is_active = payload.is_active
    
    actions = [action.model_dump() for action in payload.actions]
    wf.actions_json = json.dumps(actions)
    
    db.commit()
    db.refresh(wf)
    
    return _out(wf, actions)


@router.delete("/{id}")
def delete_workflow(
    id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Manager"]))
):
    """Remove workflow trigger settings (Admins/Managers only)."""
    wf = db.query(Workflow).filter(
        Workflow.id == id,
        Workflow.tenant_id == current_user.tenant_id
    ).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    db.delete(wf)
    db.commit()
    return {"status": "ok", "success": True}



@router.get("/{id}/runs", response_model=List[WorkflowLogOut])
def list_runs(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """The latest 50 runs of a workflow, newest first."""
    wf = db.query(Workflow).filter(Workflow.id == id, Workflow.tenant_id == current_user.tenant_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return db.query(WorkflowLog).filter(
        WorkflowLog.workflow_id == id, WorkflowLog.tenant_id == current_user.tenant_id
    ).order_by(WorkflowLog.triggered_at.desc()).limit(50).all()
