"""{{…}} placeholders in workflow messages (email, WhatsApp).

{{lead.name}}, {{lead.first_name}}, {{lead.phone}}, {{lead.email}}, {{lead.company}}, {{lead.status}}, {{custom.<key>}},
{{workspace.name}}, and for appointment triggers {{appointment.time}} ("Mon 05 Oct, 10:00 AM"), {{appointment.date}},
{{appointment.start_time}} and {{appointment.title}}, in the appointment's own timezone. Unknown ones become blank.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\.([a-z0-9_]+)\s*\}\}", re.IGNORECASE)
_LEAD_FIELDS = ("name", "phone", "email", "company", "status", "score", "assigned_agent", "follow_up_date")


def render(text: str, lead=None, workspace_name: str = "", appointment=None) -> str:
    def value(match: re.Match) -> str:
        scope, key = match.group(1).lower(), match.group(2).lower()
        if scope == "workspace" and key == "name":
            return workspace_name
        if scope == "appointment" and appointment is not None:
            return _appointment_value(appointment, key)
        if lead is None:
            return ""
        if scope == "lead":
            if key == "first_name":
                return (lead.name or "").split(" ")[0]
            if key in _LEAD_FIELDS:
                return str(getattr(lead, key) or "")
        if scope == "custom":
            return str((lead.custom_fields or {}).get(key) or "")
        return ""
    return _PLACEHOLDER.sub(value, text or "")


def _appointment_value(apt, key: str) -> str:
    if key == "title":
        return apt.title or ""
    local = datetime.fromisoformat(apt.scheduled_start).astimezone(ZoneInfo(apt.timezone or "Asia/Kolkata"))
    if key == "time":
        return local.strftime("%a %d %b, %I:%M %p")
    if key == "date":
        return local.strftime("%a %d %b %Y")
    if key == "start_time":
        return local.strftime("%I:%M %p").lstrip("0")
    return ""
