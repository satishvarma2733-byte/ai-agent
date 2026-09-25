"""Role hierarchy. A role may do everything the roles below it may do."""
from __future__ import annotations

ROLES = ("Viewer", "Agent", "Manager", "Admin", "Owner")
_RANK = {role: i for i, role in enumerate(ROLES)}
# Roles an Admin may grant through invitations or role changes. Owner is transferred, never granted.
ASSIGNABLE_ROLES = ("Viewer", "Agent", "Manager", "Admin")


def rank(role: str | None) -> int:
    return _RANK.get(role or "", -1)


def at_least(role: str | None, minimum: str) -> bool:
    return rank(role) >= rank(minimum)


def is_valid_role(role: str) -> bool:
    return role in _RANK
