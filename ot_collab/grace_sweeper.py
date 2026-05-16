"""
ot_collab/grace_sweeper.py
---------------------------
Background sweeper that closes rooms whose host grace period has expired.

Why this exists:
  When a host disconnects, we start a grace period (5 min) stored as a
  Unix timestamp in Redis (room:{room_id}:host_grace_until). If the host
  doesn't reconnect, the room should be closed automatically.

  We cannot use an asyncio.sleep task created at disconnect time because:
    - It disappears if the server process restarts (Render deploy, crash)
    - The grace timestamp is already in Redis — we just need something to
      read it on startup and periodically thereafter

Design:
  - Runs as a managed asyncio task started in FastAPI lifespan
  - On startup: immediately scans all active grace keys (crash recovery)
  - Then loops every GRACE_SWEEPER_INTERVAL seconds
  - For each expired grace key: closes the room (PG + Redis + broadcast)
  - Crash-safe: state is in Redis, not in-process memory

Registration:
  In your FastAPI app startup (main.py or app.py):

    from ot_collab.grace_sweeper import start_grace_sweeper

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(start_grace_sweeper())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
"""

from __future__ import annotations
import asyncio
import logging
import time

import db.connection as db_conn
from .models import MsgType, GRACE_SWEEPER_INTERVAL
from . import room_state
from .db import rooms as db_rooms
from .db import operations as db_ops
from .connection_manager import manager

logger = logging.getLogger(__name__)


async def start_grace_sweeper() -> None:
    """
    Entry point. Run as a long-lived asyncio task.
    Performs an immediate sweep on startup, then loops.
    """
    logger.info("[GraceSweeper] started")

    # Immediate sweep handles rooms that were in grace period before a restart
    await _sweep()

    while True:
        try:
            await asyncio.sleep(GRACE_SWEEPER_INTERVAL)
            await _sweep()
        except asyncio.CancelledError:
            logger.info("[GraceSweeper] cancelled — shutting down")
            raise
        except Exception as e:
            # Never let the sweeper crash — log and continue
            logger.error(f"[GraceSweeper] sweep error: {e}")


async def _sweep() -> None:
    """
    Scan Redis for expired grace periods and close those rooms.
    """
    now = time.time()

    try:
        grace_entries = await room_state.scan_grace_keys()
    except Exception as e:
        logger.error(f"[GraceSweeper] scan_grace_keys failed: {e}")
        return

    for room_id, grace_until in grace_entries:
        if now >= grace_until:
            logger.info(
                f"[GraceSweeper] grace expired room={room_id} "
                f"(expired {now - grace_until:.1f}s ago)"
            )
            await _close_expired_room(room_id)


async def _close_expired_room(room_id: str) -> None:
    """
    Close a room whose host grace period has expired.

    Steps:
      1. Verify room is still active in PG (may have been closed another way)
      2. Save final snapshot
      3. Mark room inactive in PG
      4. Broadcast HOST_GRACE_EXPIRED to all connected clients
      5. Expire all Redis keys
    """
    # ── 1. Verify still active ─────────────────────────────────────────────────
    try:
        async with db_conn.pool.acquire() as conn:
            room = await db_rooms.get_room(conn, room_id)
    except Exception as e:
        logger.error(f"[GraceSweeper] get_room failed room={room_id}: {e}")
        return

    if not room or not room["is_active"]:
        # Already closed — just clean up the stale grace key
        await room_state.clear_host_grace(room_id)
        return

    # ── 2. Save final snapshot ─────────────────────────────────────────────────
    try:
        content, revision = await room_state.get_room_doc(room_id)
        async with db_conn.pool.acquire() as conn:
            await db_ops.save_snapshot(conn, room_id, content, revision)
            await db_rooms.update_room_revision(conn, room_id, revision)
    except KeyError:
        # Redis already cold — PG has the last known state, that's fine
        logger.warning(f"[GraceSweeper] room={room_id} Redis cold at close time, skipping snapshot")
    except Exception as e:
        logger.error(f"[GraceSweeper] snapshot failed room={room_id}: {e}")

    # ── 3. Mark PG inactive ────────────────────────────────────────────────────
    try:
        async with db_conn.pool.acquire() as conn:
            await db_rooms.set_room_inactive(conn, room_id)
    except Exception as e:
        logger.error(f"[GraceSweeper] set_room_inactive failed room={room_id}: {e}")
        # Continue — still want to broadcast and clean Redis

    # ── 4. Broadcast to connected clients ─────────────────────────────────────
    try:
        await manager.broadcast(room_id, {
            "type":    MsgType.HOST_GRACE_EXPIRED,
            "message": "Host did not reconnect. The room has been closed.",
        })
    except Exception as e:
        logger.error(f"[GraceSweeper] broadcast failed room={room_id}: {e}")

    # ── 5. Expire Redis ────────────────────────────────────────────────────────
    try:
        await room_state.expire_room(room_id)
    except Exception as e:
        logger.error(f"[GraceSweeper] expire_room failed room={room_id}: {e}")

    logger.info(f"[GraceSweeper] room={room_id} closed after grace period expiry")