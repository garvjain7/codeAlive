"""
ot_collab/handlers/ops.py
--------------------------
Handles incoming op and cursor messages.

_handle_op is the hot path — called on every keystroke.
Keep it fast: Redis only, no PG on the critical path.
PG writes (persist_op, snapshot) are always background tasks.
"""

from __future__ import annotations
import json
import logging

from fastapi import WebSocket, BackgroundTasks

import db.connection as db_conn
from ..models import (
    MsgType, ClientOpMessage, NoOp,
    SNAPSHOT_EVERY_N_OPS,
)
from .. import ot_engine, room_state
from ..db import operations as db_ops
from ..db import rooms as db_rooms
from ..connection_manager import manager

logger = logging.getLogger(__name__)


async def handle_op(
    websocket:  WebSocket,
    msg:        dict,
    room_id:    str,
    user_id:    str,
    background: BackgroundTasks,
) -> None:
    """
    Critical path — handle an incoming operation.

    Steps:
      1. Parse + validate ClientOpMessage
      2. Mute check — reject op silently if user is muted
      3. Grace period check — reject op if room is suspended
      4. Fetch history since client_revision
      5. Transform op against concurrent history
      6. NoOp check — ack without applying if transform yields NoOp
      7. Atomic apply to Redis (WATCH/MULTI/EXEC)
      8. Ack sender with new revision + transformed op
      9. Broadcast to all other participants
     10. Background: persist op to PG
     11. Background: maybe save snapshot
    """
    # ── 1. Parse ──────────────────────────────────────────────────────────────
    try:
        client_msg = ClientOpMessage.from_dict(msg)
    except (KeyError, ValueError, TypeError) as e:
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "invalid_op",
            "message": f"Malformed operation: {e}",
        }))
        return

    op              = client_msg.op
    op_id           = client_msg.op_id
    client_revision = client_msg.client_revision

    # ── 2. Mute check ─────────────────────────────────────────────────────────
    # Fast Redis read — no PG call on the hot path.
    if await room_state.is_user_muted(room_id, user_id):
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "muted",
            "message": "You have been muted and cannot send operations.",
        }))
        return

    # ── 3. Grace period check ─────────────────────────────────────────────────
    # If room is in host grace period, editing is suspended for everyone.
    grace_until = await room_state.get_host_grace(room_id)
    if grace_until is not None:
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "room_suspended",
            "message": "Room is suspended while waiting for host to reconnect.",
        }))
        return

    # ── 4. Fetch history ───────────────────────────────────────────────────────
    try:
        history_ops = await room_state.get_history_since(room_id, client_revision)
    except Exception as e:
        logger.error(f"[Op] get_history_since failed room={room_id}: {e}")
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "server_error",
            "message": "Failed to fetch operation history.",
        }))
        return

    # ── 5. Transform ───────────────────────────────────────────────────────────
    transformed = ot_engine.transform_against_many(op, history_ops) if history_ops else op

    # ── 6. NoOp check ─────────────────────────────────────────────────────────
    if isinstance(transformed, NoOp):
        try:
            _, current_rev = await room_state.get_room_doc(room_id)
        except KeyError:
            current_rev = client_revision
        await websocket.send_text(json.dumps({
            "type":     MsgType.OP_ACK,
            "op_id":    op_id,
            "revision": current_rev,
            "op":       op.to_dict(),
        }))
        return

    # ── 7. Atomic apply ───────────────────────────────────────────────────────
    try:
        _, new_revision = await room_state.apply_op_to_room(room_id, transformed)
    except ValueError as e:
        logger.error(f"[Op] apply failed room={room_id} user={user_id}: {e}")
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "apply_failed",
            "message": "Operation could not be applied. Please reconnect.",
        }))
        return
    except RuntimeError as e:
        logger.error(f"[Op] retries exhausted room={room_id}: {e}")
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "server_error",
            "message": "Server under heavy load. Please retry.",
        }))
        return

    # ── 8. Ack sender ──────────────────────────────────────────────────────────
    await websocket.send_text(json.dumps({
        "type":     MsgType.OP_ACK,
        "op_id":    op_id,
        "revision": new_revision,
        "op":       transformed.to_dict(),
    }))

    # ── 9. Broadcast ───────────────────────────────────────────────────────────
    await manager.broadcast(room_id, {
        "type":     MsgType.OP_BROADCAST,
        "op":       transformed.to_dict(),
        "revision": new_revision,
        "user_id":  user_id,
    }, exclude_user_id=user_id)

    # ── 10. Persist op (background) ────────────────────────────────────────────
    async def _persist():
        try:
            async with db_conn.pool.acquire() as conn:
                await db_ops.persist_op(
                    conn, room_id, user_id, op_id, new_revision, transformed
                )
        except Exception as e:
            logger.error(f"[Op] persist_op failed room={room_id} rev={new_revision}: {e}")

    background.add_task(_persist)

    # ── 11. Maybe snapshot (background) ────────────────────────────────────────
    if new_revision % SNAPSHOT_EVERY_N_OPS == 0:
        async def _snapshot():
            try:
                content, rev = await room_state.get_room_doc(room_id)
                async with db_conn.pool.acquire() as conn:
                    await db_ops.save_snapshot(conn, room_id, content, rev)
                    await db_rooms.update_room_revision(conn, room_id, rev)
            except Exception as e:
                logger.error(f"[Op] snapshot failed room={room_id}: {e}")

        background.add_task(_snapshot)


async def handle_cursor(msg: dict, room_id: str, user_id: str) -> None:
    """
    Update cursor position in Redis and broadcast to room.
    Lossy — no ack, no PG write. If it fails, next cursor message corrects it.
    """
    try:
        line = int(msg.get("line", 1))
        col  = int(msg.get("col",  0))
    except (TypeError, ValueError):
        return

    await room_state.update_user_cursor(room_id, user_id, line, col)
    await manager.broadcast(room_id, {
        "type":    MsgType.CURSOR_BROADCAST,
        "user_id": user_id,
        "line":    line,
        "col":     col,
    }, exclude_user_id=user_id)