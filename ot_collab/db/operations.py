"""
ot_collab/db/operations.py
---------------------------
PostgreSQL queries for OT operation persistence and snapshots.
Coordinates with the schema in schema.sql.
"""

from __future__ import annotations
import uuid
import logging
from typing import Optional

from . import rooms as db_rooms

logger = logging.getLogger(__name__)

async def persist_op(
    conn, 
    room_id:  str, 
    user_id:  str, 
    op_id:    str, 
    revision: int, 
    op:       any
) -> None:
    """
    Persist a single transformed operation to the operation_log.
    UNIQUE(room_id, revision) ensures we never have two ops at the same rev.
    UNIQUE(op_id) ensures client retries are idempotent.
    """
    await conn.execute("""
        INSERT INTO operation_log (
            room_id, user_id, op_id, revision, 
            op_type, position, chars, length
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (op_id) DO NOTHING
    """, 
    uuid.UUID(room_id), 
    uuid.UUID(user_id), 
    op_id, 
    revision,
    op.op_type.value,
    op.position,
    op.chars,
    op.length)


async def save_snapshot(
    conn, 
    room_id:  str, 
    content:  str, 
    revision: int
) -> None:
    """
    Save a document snapshot. 
    Used for cold-start recovery and durability.
    """
    await conn.execute("""
        INSERT INTO document_snapshots (room_id, content, revision)
        VALUES ($1, $2, $3)
        ON CONFLICT (room_id, revision) DO UPDATE 
        SET content = EXCLUDED.content
    """, uuid.UUID(room_id), content, revision)


async def recover_room_state(conn, room_id: str) -> dict:
    """
    Recover full room state from PG for cold-start (e.g. after server restart).
    Returns {content, revision, host_id, cohost_id, is_locked, password_version}.
    """
    # 1. Get room metadata
    room = await db_rooms.get_room(conn, room_id)
    if not room:
        raise ValueError(f"Room {room_id} not found in PostgreSQL")

    # 2. Get latest snapshot
    row = await conn.fetchrow("""
        SELECT content, revision FROM document_snapshots
        WHERE room_id = $1
        ORDER BY revision DESC
        LIMIT 1
    """, uuid.UUID(room_id))

    if row:
        content  = row["content"]
        revision = row["revision"]
    else:
        content  = ""
        revision = 0

    return {
        "content":          content,
        "revision":         revision,
        "host_id":          str(room["host_id"]),
        "cohost_id":        str(room["cohost_id"]) if room["cohost_id"] else None,
        "is_locked":        room["is_locked"],
        "password_version": room["password_version"],
    }