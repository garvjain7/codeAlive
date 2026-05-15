"""
ot_collab/db/operations.py
--------------------------
PostgreSQL queries for operation_log and document_snapshots.

operation_log is the WAL (Write-Ahead Log) of the collaboration system.
document_snapshots are checkpoints.
Recovery = latest snapshot + replay ops since that revision via ot_engine.apply().

persist_op() is called as a BackgroundTask — NOT on the critical path.
The op is already applied to Redis before this is called.
If this fails, the op lives in Redis history until the next snapshot catches up.
"""

from __future__ import annotations
import uuid
from typing import Optional

from ..models import Op, OpType


# ── Operation log ─────────────────────────────────────────────────────────────

async def persist_op(
    conn,
    room_id:  str,
    user_id:  str,
    op_id:    str,      # client-generated idempotency key
    revision: int,      # server revision AFTER this op applied
    op:       Op,
) -> None:
    """
    Persist an applied op to the operation log.

    ON CONFLICT ON op_id → DO NOTHING
      Idempotency: if client retries and server processes twice,
      second insert is silently ignored.

    ON CONFLICT ON (room_id, revision) should NEVER fire in production.
    If it does, it means the Redis WATCH lock failed to prevent a race.
    We let it raise — it's a bug signal, not a recoverable error.
    """
    await conn.execute("""
        INSERT INTO operation_log
            (room_id, user_id, op_id, revision, op_type, position, chars, length)
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
        op.length,
    )


async def get_ops_since(conn, room_id: str, since_revision: int) -> list[Op]:
    """
    Fetch ops from operation_log since a given revision.

    This is the fallback for when Redis history is cold (server restart).
    Normally, get_history_since() in room_state.py serves this from Redis.
    This is only called during room recovery from cold start.

    Returns ops in ascending revision order.
    """
    rows = await conn.fetch("""
        SELECT op_type, position, chars, length
        FROM operation_log
        WHERE room_id = $1 AND revision > $2
        ORDER BY revision ASC
    """, uuid.UUID(room_id), since_revision)
    return [
        Op(
            op_type=OpType(r["op_type"]),
            position=r["position"],
            chars=r["chars"],
            length=r["length"],
        )
        for r in rows
    ]


# ── Snapshots ─────────────────────────────────────────────────────────────────

async def save_snapshot(
    conn,
    room_id:  str,
    content:  str,
    revision: int,
) -> None:
    """
    Save a document snapshot.

    ON CONFLICT DO NOTHING — if somehow called twice at same revision,
    first write wins. This is safe because content at a given revision
    is deterministic.
    """
    await conn.execute("""
        INSERT INTO document_snapshots (room_id, content, revision)
        VALUES ($1, $2, $3)
        ON CONFLICT (room_id, revision) DO NOTHING
    """, uuid.UUID(room_id), content, revision)


async def get_latest_snapshot(conn, room_id: str) -> Optional[dict]:
    """
    Fetch the most recent snapshot for a room.
    Returns None if no snapshots exist (brand new room).

    Used during room recovery after Redis cold-start.
    """
    row = await conn.fetchrow("""
        SELECT content, revision, created_at
        FROM document_snapshots
        WHERE room_id = $1
        ORDER BY revision DESC
        LIMIT 1
    """, uuid.UUID(room_id))
    return dict(row) if row else None


# ── Room recovery ─────────────────────────────────────────────────────────────

async def recover_room_state(conn, room_id: str) -> tuple[str, int]:
    """
    Reconstruct current document state from PostgreSQL.

    Called when Redis is cold (server restart, Redis flush).
    Returns (content, revision) ready to seed back into Redis.

    Algorithm (ARIES-style recovery):
      1. Find latest snapshot → content at revision R
      2. Fetch all ops since revision R from operation_log
      3. Replay each op via ot_engine.apply()
      4. Return final (content, current_revision)

    If no snapshot exists, start from empty string at revision 0.
    This handles brand-new rooms that have no snapshot yet.
    """
    from .. import ot_engine  # local import to avoid circular

    snapshot = await get_latest_snapshot(conn, room_id)

    if snapshot:
        content  = snapshot["content"]
        base_rev = snapshot["revision"]
    else:
        content  = ""
        base_rev = 0

    ops = await get_ops_since(conn, room_id, base_rev)

    for op in ops:
        content = ot_engine.apply(content, op)

    # Current revision = snapshot revision + number of replayed ops
    current_rev = base_rev + len(ops)

    return content, current_rev