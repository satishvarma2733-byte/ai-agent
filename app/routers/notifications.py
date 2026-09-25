"""The signed-in member's notifications."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import UTCDateTime

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


class NotificationOut(BaseModel):
    id: str
    kind: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    created_at: UTCDateTime
    read: bool


class NotificationsOut(BaseModel):
    unread: int
    items: List[NotificationOut]


def _mine(db: Session, user: User):
    return db.query(Notification).filter(Notification.user_id == user.id, Notification.tenant_id == user.tenant_id)


@router.get("", response_model=NotificationsOut)
def list_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The 30 most recent, newest first, with the unread count."""
    rows = _mine(db, current_user).order_by(Notification.created_at.desc()).limit(30).all()
    unread = _mine(db, current_user).filter(Notification.read_at.is_(None)).count()
    return NotificationsOut(unread=unread, items=[
        NotificationOut(id=r.id, kind=r.kind, title=r.title, body=r.body, link=r.link, created_at=r.created_at,
                        read=r.read_at is not None) for r in rows])


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def read_all(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _mine(db, current_user).filter(Notification.read_at.is_(None)).update({Notification.read_at: now}, synchronize_session=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_all(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _mine(db, current_user).delete(synchronize_session=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_one(notification_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not _mine(db, current_user).filter(Notification.id == notification_id).delete(synchronize_session=False):
        raise HTTPException(status_code=404, detail="Notification not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
