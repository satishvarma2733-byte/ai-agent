"""Tasks: to-dos for teammates, optionally about a lead, with due dates. Anyone but a Viewer can create
and complete tasks; assigning one to someone else notifies them."""
from datetime import date, datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.models.lead import Lead
from app.models.task import Task
from app.models.user import User
from app.schemas.common import UTCDateTime
from app.services import notifications

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    due_date: Optional[date] = None
    assigned_user_id: Optional[str] = None
    lead_id: Optional[str] = None


class TaskPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    due_date: Optional[date] = None
    assigned_user_id: Optional[str] = None
    status: Optional[Literal["open", "done"]] = None


class TaskOut(BaseModel):
    id: str
    title: str
    notes: Optional[str] = None
    due_date: Optional[str] = None
    assigned_user_id: Optional[str] = None
    assigned_name: Optional[str] = None
    lead_id: Optional[str] = None
    lead_name: Optional[str] = None
    status: str
    overdue: bool
    created_at: UTCDateTime
    completed_at: Optional[UTCDateTime] = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _member(db: Session, tenant_id: str, user_id: Optional[str]) -> Optional[User]:
    if not user_id:
        return None
    from app.services import memberships
    row = memberships.members(db, tenant_id, active_only=True).filter(User.id == user_id).first()
    user = row[0] if row else None
    if user is None:
        raise HTTPException(status_code=422, detail="Assign the task to an active member of this workspace.")
    return user


def _out(db: Session, task: Task) -> TaskOut:
    assignee = db.get(User, task.assigned_user_id) if task.assigned_user_id else None
    lead = db.get(Lead, task.lead_id) if task.lead_id else None
    return TaskOut(id=task.id, title=task.title, notes=task.notes, due_date=task.due_date,
                   assigned_user_id=task.assigned_user_id, assigned_name=assignee.name if assignee else None,
                   lead_id=task.lead_id, lead_name=lead.name if lead else None, status=task.status,
                   overdue=bool(task.status == "open" and task.due_date and task.due_date < date.today().isoformat()),
                   created_at=task.created_at, completed_at=task.completed_at)


def _notify_assignee(db: Session, task: Task, by: User) -> None:
    if task.assigned_user_id and task.assigned_user_id != by.id:
        due = f" (due {task.due_date})" if task.due_date else ""
        notifications.notify(db, task.tenant_id, [task.assigned_user_id], kind="task_assigned",
                             title=f"{by.name or by.email} gave you a task{due}", body=task.title, link="/tasks")


@router.get("", response_model=List[TaskOut])
def list_tasks(mine: bool = False, status: Literal["open", "done", "all"] = "open", lead_id: Optional[str] = None,
               limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """Open tasks first by due date (tasks without one last)."""
    query = db.query(Task).filter(Task.tenant_id == current_user.tenant_id)
    if mine:
        query = query.filter(Task.assigned_user_id == current_user.id)
    if status != "all":
        query = query.filter(Task.status == status)
    if lead_id:
        query = query.filter(Task.lead_id == lead_id)
    rows = query.order_by(Task.due_date.is_(None), Task.due_date, Task.created_at).limit(limit).all()
    return [_out(db, t) for t in rows]


@router.post("", response_model=TaskOut, status_code=201)
def create_task(payload: TaskIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _member(db, current_user.tenant_id, payload.assigned_user_id)
    if payload.lead_id and not db.query(Lead.id).filter(Lead.id == payload.lead_id, Lead.tenant_id == current_user.tenant_id).first():
        raise HTTPException(status_code=404, detail="Lead not found")
    task = Task(tenant_id=current_user.tenant_id, title=payload.title.strip(), notes=payload.notes,
                due_date=payload.due_date.isoformat() if payload.due_date else None,
                assigned_user_id=payload.assigned_user_id or current_user.id, lead_id=payload.lead_id,
                created_by=current_user.id, created_at=_now())
    db.add(task)
    db.commit()
    _notify_assignee(db, task, current_user)
    return _out(db, task)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, payload: TaskPatch, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.tenant_id == current_user.tenant_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    fields = payload.model_dump(exclude_unset=True)
    reassigned = "assigned_user_id" in fields and fields["assigned_user_id"] != task.assigned_user_id
    if reassigned:
        _member(db, current_user.tenant_id, fields["assigned_user_id"])
    for key, value in fields.items():
        if key == "due_date":
            value = value.isoformat() if value else None
        setattr(task, key, value.strip() if key == "title" and value else value)
    if "status" in fields:
        task.completed_at = _now() if fields["status"] == "done" else None
    db.commit()
    if reassigned:
        _notify_assignee(db, task, current_user)
    return _out(db, task)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not db.query(Task).filter(Task.id == task_id, Task.tenant_id == current_user.tenant_id).delete():
        raise HTTPException(status_code=404, detail="Task not found")
    db.commit()
    return Response(status_code=204)
