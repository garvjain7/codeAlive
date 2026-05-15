"""
ot_collab/models.py
-------------------
All data models for the OT collaboration system.

Two categories:
  1. Op / OpType — pure data, used by ot_engine.py and room_state.py
  2. WS message models — what travels over the WebSocket wire

Nothing in this file does I/O. Everything else imports from here.
"""

from __future__ import annotations
from dataclasses import dataclass, field
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
    For multi-char ops (paste, delete-word), chars/length > 1.
    """
    op_type:  OpType
    position: int
    chars:    Optional[str] = None   # insert only
    length:   Optional[int] = None   # delete only

    def __post_init__(self):
        if self.op_type == OpType.INSERT:
            if not self.chars:
                raise ValueError("Insert op must have chars")
            self.length = len(self.chars)   # always derived, never trusted from wire
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
# Returned by transform() when a delete is completely cancelled by a concurrent
# delete of the same range. The caller must check for this before applying.

class NoOp:
    """Sentinel: operation was rendered moot by a concurrent op."""
    pass


# ── WebSocket message types ───────────────────────────────────────────────────
# These are the strings that go in the "type" field of every WS message.

class MsgType:
    # Client → Server
    OP              = "op"              # client sends an operation
    CURSOR          = "cursor"          # client sends cursor position
    APPROVE_USER    = "approve_user"    # host approves a join request
    REJECT_USER     = "reject_user"     # host rejects a join request
    CLOSE_ROOM      = "close_room"      # host closes the room

    # Server → Client
    OP_ACK          = "op_ack"          # server confirms op applied (to sender)
    OP_BROADCAST    = "op_broadcast"    # server broadcasts op (to others)
    CURSOR_BROADCAST = "cursor_broadcast"
    JOIN_REQUEST    = "join_request"    # server notifies host of pending user
    JOIN_APPROVED   = "join_approved"   # server tells user they're in
    JOIN_REJECTED   = "join_rejected"   # server tells user they're out
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT   = "participant_left"
    HOST_DISCONNECTED  = "host_disconnected"
    ROOM_CLOSED        = "room_closed"
    ERROR              = "error"


# ── Inbound WS messages (Client → Server) ─────────────────────────────────────

@dataclass
class ClientOpMessage:
    """
    Client sends this when the user makes an edit.

    op_id: client-generated UUID — idempotency key.
           If the server receives the same op_id twice (network retry),
           the second is silently ignored.

    client_revision: the confirmed_doc.revision the client was at when
                     this op was generated. Server uses this to know
                     which history ops to transform against.
    """
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
    """Lossy — sent at 50ms debounce, dropped if slow."""
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
class ApproveRejectMessage:
    """Host approves or rejects a waiting user."""
    target_user_id: str
    room_id:        str

    @classmethod
    def from_dict(cls, d: dict) -> ApproveRejectMessage:
        return cls(
            target_user_id=d["target_user_id"],
            room_id=d["room_id"],
        )


# ── Outbound WS messages (Server → Client) ────────────────────────────────────
# These are plain dicts built inline in ws_router.py.
# Kept as documented constants here for reference.

"""
op_ack → sender:
{
    "type":     "op_ack",
    "op_id":    str,        # echo of client's op_id
    "revision": int,        # new server revision
    "op":       Op.to_dict  # transformed op (may differ from sent op)
}

op_broadcast → all others:
{
    "type":     "op_broadcast",
    "op":       Op.to_dict,
    "revision": int,
    "user_id":  str
}

join_approved → new participant:
{
    "type":     "join_approved",
    "content":  str,        # full document content at this moment
    "revision": int,        # current server revision
    "users":    [           # currently connected users for presence
        {"user_id": str, "username": str, "color": str}
    ]
}

join_request → host:
{
    "type":        "join_request",
    "user_id":     str,
    "username":    str,
    "request_id":  str
}

participant_joined → all:
{
    "type":     "participant_joined",
    "user_id":  str,
    "username": str,
    "color":    str
}

participant_left → all:
{
    "type":    "participant_left",
    "user_id": str
}

host_disconnected → all:
{
    "type": "host_disconnected"
}

room_closed → all:
{
    "type": "room_closed"
}

error → sender:
{
    "type":    "error",
    "code":    str,     # machine-readable: "room_not_found", "not_participant", etc.
    "message": str      # human-readable
}
"""


# ── User color pool ───────────────────────────────────────────────────────────
# Assigned on join, stored in Redis room users hash.
# Chosen to be visually distinct on dark backgrounds (oneDark theme).

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
    # All taken — cycle from start (>8 participants)
    return PARTICIPANT_COLORS[len(existing_colors) % len(PARTICIPANT_COLORS)]


# ── Snapshot trigger ──────────────────────────────────────────────────────────

SNAPSHOT_EVERY_N_OPS = 50   # write a snapshot every N operations
ROOM_TTL_SECONDS     = 86400  # 24 hours
JOIN_TIMEOUT_SECONDS = 120    # 2 minutes for host to approve