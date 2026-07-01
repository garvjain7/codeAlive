"""
ot_collab/models.py
-------------------
All data models for the OT collaboration system.

Three categories:
  1. Op / OpType          — pure OT primitives
  2. ParticipantRole      — role enum used by permissions + Redis + PG
  3. WS message types     — MsgType constants + inbound message dataclasses

Nothing in this file does I/O.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import json


# ── Op primitives ─────────────────────────────────────────────────────────────

class OpType(str, Enum):
    INSERT = "insert"
    DELETE = "delete"


@dataclass
class Op:
    """
    A single string-level operation.

    Insert: position + chars (length derived from len(chars))
    Delete: position + length (chars is None)

    position is always a character offset from the start of the document.
    """
    op_type:  OpType
    position: int
    chars:    Optional[str] = None
    length:   Optional[int] = None

    def __post_init__(self):
        if self.op_type == OpType.INSERT:
            if not self.chars:
                raise ValueError("Insert op must have chars")
            self.length = len(self.chars)
        elif self.op_type == OpType.DELETE:
            if self.length is None or self.length <= 0:
                raise ValueError("Delete op must have length > 0")
            self.chars = None

    def to_dict(self) -> dict:
        return {
            "op_type":  self.op_type.value,
            "position": self.position,
            "chars":    self.chars,
            "length":   self.length,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Op:
        return cls(
            op_type=OpType(d["op_type"]),
            position=int(d["position"]),
            chars=d.get("chars"),
            length=int(d["length"]) if d.get("length") is not None else None,
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, s: str) -> Op:
        return cls.from_dict(json.loads(s))


# ── No-op sentinel ─────────────────────────────────────────────────────────────

class NoOp:
    """Sentinel: operation was rendered moot by a concurrent op."""
    pass


# ── Participant role ───────────────────────────────────────────────────────────

class ParticipantRole(str, Enum):
    HOST        = "host"
    COHOST      = "cohost"
    PARTICIPANT = "participant"


# ── WebSocket message types ───────────────────────────────────────────────────

class MsgType:
    # ── Client → Server ───────────────────────────────────────────────────────
    OP              = "op"
    CURSOR          = "cursor"
    PASSWORD_SUBMIT = "password_submit"   # user submits room password
    APPROVE_USER    = "approve_user"      # host/cohost approves join request
    REJECT_USER     = "reject_user"       # host/cohost rejects join request
    KICK_USER       = "kick_user"         # host/cohost removes participant
    MUTE_USER       = "mute_user"         # host/cohost silences participant
    UNMUTE_USER     = "unmute_user"       # host/cohost restores participant
    PROMOTE_COHOST  = "promote_cohost"    # host only — elevates participant
    DEMOTE_COHOST   = "demote_cohost"     # host only — removes cohost
    LOCK_ROOM       = "lock_room"         # host/cohost — no new joins
    UNLOCK_ROOM     = "unlock_room"       # host/cohost — allow joins again
    SET_PASSWORD    = "set_password"      # host only — set/change/clear password
    CLOSE_ROOM      = "close_room"        # host only — permanently end room

    # ── Server → Client ───────────────────────────────────────────────────────
    # Op flow
    OP_ACK             = "op_ack"
    OP_BROADCAST       = "op_broadcast"
    CURSOR_BROADCAST   = "cursor_broadcast"

    # Password gate
    PASSWORD_REQUIRED  = "password_required"   # room has password, please submit
    PASSWORD_ACCEPTED  = "password_accepted"   # correct, proceeding to join flow
    PASSWORD_REJECTED  = "password_rejected"   # wrong password

    # Join flow
    JOIN_REQUEST       = "join_request"        # host notified of pending user
    JOIN_APPROVED      = "join_approved"       # user admitted to room
    JOIN_REJECTED      = "join_rejected"       # user denied or timed out

    # Presence
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT   = "participant_left"

    # Moderation — targeted
    YOU_WERE_KICKED    = "you_were_kicked"
    YOU_WERE_MUTED     = "you_were_muted"
    YOU_WERE_UNMUTED   = "you_were_unmuted"

    # Moderation — broadcast (so all clients update their UI)
    PARTICIPANT_KICKED = "participant_kicked"
    PARTICIPANT_MUTED  = "participant_muted"
    PARTICIPANT_UNMUTED= "participant_unmuted"

    # Role changes — broadcast
    COHOST_PROMOTED    = "cohost_promoted"
    COHOST_DEMOTED     = "cohost_demoted"

    # Room state — broadcast
    ROOM_LOCKED        = "room_locked"
    ROOM_UNLOCKED      = "room_unlocked"
    ROOM_CLOSED        = "room_closed"
    PASSWORD_CHANGED   = "password_changed"    # broadcast so clients know auth cache is stale

    # Host lifecycle
    HOST_DISCONNECTED  = "host_disconnected"   # grace period starts
    HOST_REJOINED      = "host_rejoined"       # grace period cancelled
    HOST_GRACE_EXPIRED = "host_grace_expired"  # grace period ended, room closing

    # Generic
    ERROR              = "error"


# ── Inbound WS message dataclasses ────────────────────────────────────────────

@dataclass
class ClientOpMessage:
    op_id:           str
    room_id:         str
    op:              Op
    client_revision: int

    @classmethod
    def from_dict(cls, d: dict) -> ClientOpMessage:
        return cls(
            op_id=d["op_id"],
            room_id=d["room_id"],
            op=Op.from_dict(d["op"]),
            client_revision=int(d["client_revision"]),
        )


@dataclass
class CursorMessage:
    room_id: str
    line:    int
    col:     int

    @classmethod
    def from_dict(cls, d: dict) -> CursorMessage:
        return cls(
            room_id=d["room_id"],
            line=int(d["line"]),
            col=int(d["col"]),
        )


@dataclass
class PasswordSubmitMessage:
    room_id:  str
    password: str    # plaintext — hashed server-side immediately

    @classmethod
    def from_dict(cls, d: dict) -> PasswordSubmitMessage:
        return cls(
            room_id=d["room_id"],
            password=d["password"],
        )


@dataclass
class ApproveRejectMessage:
    target_user_id: str
    room_id:        str
    request_id:     str

    @classmethod
    def from_dict(cls, d: dict) -> ApproveRejectMessage:
        return cls(
            target_user_id=d["target_user_id"],
            room_id=d["room_id"],
            request_id=d["request_id"],
        )


@dataclass
class TargetUserMessage:
    """
    Generic single-target moderation message.
    Used for: kick, mute, unmute, promote, demote.
    """
    target_user_id: str
    room_id:        str

    @classmethod
    def from_dict(cls, d: dict) -> TargetUserMessage:
        return cls(
            target_user_id=d["target_user_id"],
            room_id=d["room_id"],
        )


@dataclass
class SetPasswordMessage:
    room_id:  str
    password: Optional[str]   # None = clear password (remove protection)

    @classmethod
    def from_dict(cls, d: dict) -> SetPasswordMessage:
        return cls(
            room_id=d["room_id"],
            password=d.get("password") or None,
        )


# ── User color pool ───────────────────────────────────────────────────────────

PARTICIPANT_COLORS = [
    "#64b5f6",  # blue
    "#4caf50",  # green
    "#ef9f27",  # amber
    "#e040fb",  # purple
    "#ef5350",  # red
    "#26c6da",  # cyan
    "#ffca28",  # yellow
    "#ff7043",  # deep orange
]

def assign_color(existing_colors: list[str]) -> str:
    """Pick the first color from the pool not already in use."""
    for c in PARTICIPANT_COLORS:
        if c not in existing_colors:
            return c
    return PARTICIPANT_COLORS[len(existing_colors) % len(PARTICIPANT_COLORS)]


# ── System constants ──────────────────────────────────────────────────────────

SNAPSHOT_EVERY_N_OPS   = 50     # write a PG snapshot every N operations
ROOM_TTL_SECONDS       = 86400  # 24 hours — Redis key lifetime
JOIN_TIMEOUT_SECONDS   = 120    # 2 minutes for host to approve a join request
GRACE_PERIOD_SECONDS   = 300    # 5 minutes for host to reconnect after disconnect
GRACE_SWEEPER_INTERVAL = 30     # sweeper wakes every 30 seconds