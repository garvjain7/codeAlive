"""
ot_collab/permissions.py
------------------------
Pure permission logic. Zero I/O. Zero side effects.

Single source of truth for every role-based check in the system.
ws_router.py and every handler import from here — no inline role
string comparisons anywhere else in the codebase.

All functions take a ParticipantRole (or raw string) and return bool.
Callers are responsible for fetching the role; this file only decides
what that role is allowed to do.

Permission matrix:

Action                  host    cohost  participant
----------------------- ------- ------- -----------
send ops                yes     yes     yes (if not muted)
send cursor             yes     yes     yes
approve/reject joins    yes     yes     no
kick participant        yes     yes     no
mute/unmute             yes     yes     no
promote to cohost       yes     no      no
demote cohost           yes     no      no
lock/unlock room        yes     yes     no
set/clear password      yes     no      no
close room              yes     no      no
"""

from __future__ import annotations
from .models import ParticipantRole


def _role(role: str | ParticipantRole) -> ParticipantRole:
    """Normalize raw string to enum. Raises ValueError on unknown role."""
    if isinstance(role, ParticipantRole):
        return role
    return ParticipantRole(role)


def is_elevated(role: str | ParticipantRole) -> bool:
    """True for host or cohost — both have moderation authority."""
    r = _role(role)
    return r in (ParticipantRole.HOST, ParticipantRole.COHOST)


def can_approve_joins(role: str | ParticipantRole) -> bool:
    return is_elevated(role)


def can_kick(role: str | ParticipantRole) -> bool:
    return is_elevated(role)


def can_mute(role: str | ParticipantRole) -> bool:
    return is_elevated(role)


def can_lock_room(role: str | ParticipantRole) -> bool:
    return is_elevated(role)


def can_promote_cohost(role: str | ParticipantRole) -> bool:
    """Only the host can promote someone to cohost."""
    return _role(role) == ParticipantRole.HOST


def can_demote_cohost(role: str | ParticipantRole) -> bool:
    """Only the host can demote the cohost."""
    return _role(role) == ParticipantRole.HOST


def can_set_password(role: str | ParticipantRole) -> bool:
    """Only the host can set or clear the room password."""
    return _role(role) == ParticipantRole.HOST


def can_close_room(role: str | ParticipantRole) -> bool:
    """Only the host can permanently close the room."""
    return _role(role) == ParticipantRole.HOST


def can_send_op(role: str | ParticipantRole, is_muted: bool) -> bool:
    """
    Any non-muted participant can send ops.
    Muted check is separate from role check — a cohost can also be muted
    (edge case but possible if host mutes before promoting, ordering matters).
    """
    return not is_muted


def assert_elevated(role: str | ParticipantRole, action: str) -> None:
    """
    Raise PermissionError if role is not host or cohost.
    Use in handlers to fail fast with a descriptive message.
    """
    if not is_elevated(role):
        raise PermissionError(f"Action '{action}' requires host or cohost role.")


def assert_host(role: str | ParticipantRole, action: str) -> None:
    """
    Raise PermissionError if role is not host.
    Use for host-only actions: close room, set password, promote/demote.
    """
    if _role(role) != ParticipantRole.HOST:
        raise PermissionError(f"Action '{action}' requires host role.")