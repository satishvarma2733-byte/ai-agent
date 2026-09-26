"""@mentions in lead notes: "@Asha" (first name), "@asha.rao" (email name) or "@AshaRao" (name without spaces)
notifies that teammate. Unknown or ambiguous names are ignored."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.user import User

_MENTION = re.compile(r"(?<![\w@])@([A-Za-z][\w.\-]{1,60})")


def mentioned_users(db: Session, tenant_id: str, text: str) -> list[User]:
    tokens = {m.group(1).rstrip(".").lower() for m in _MENTION.finditer(text or "")}
    if not tokens:
        return []
    members = db.query(User).filter(User.tenant_id == tenant_id, User.status == "active").all()
    found: dict[str, User] = {}
    for token in tokens:
        matches = [u for u in members if token in {
            (u.name or "").split(" ")[0].lower(),
            (u.name or "").replace(" ", "").lower(),
            u.email.split("@")[0].lower(),
        }]
        if len(matches) == 1:  # "@Asha" with two Ashas notifies no one rather than the wrong one
            found[matches[0].id] = matches[0]
    return list(found.values())


def notify_mentions(db: Session, tenant_id: str, text: str, author: User, *, about: str, link: str) -> int:
    from app.services import notifications
    users = [u for u in mentioned_users(db, tenant_id, text) if u.id != author.id]
    if users:
        notifications.notify(db, tenant_id, [u.id for u in users], kind="mention",
                             title=f"{author.name or author.email} mentioned you on {about}", body=(text or "")[:200], link=link)
    return len(users)
