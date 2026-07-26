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
from datetime import datetime, timedelta

import db.connection as db_conn
from .models import MsgType, GRACE_SWEEPER_INTERVAL
from . import room_state
from .db import rooms as db_rooms
from .db import operations as db_ops
from .connection_manager import manager
from core.config import ENABLE_ROOMS

logger = logging.getLogger(__name__)


async def start_grace_sweeper() -> None:
    """
    Entry point. Run as a long-lived asyncio task.
    Performs an immediate sweep on startup, then loops.
    """
    if not ENABLE_ROOMS:
        logger.info("[GraceSweeper] disabled (ENABLE_ROOMS=False)")
        return

    logger.info("[GraceSweeper] started")

    # Immediate sweep handles rooms that were in grace period before a restart
    try:
        await _sweep_grace_periods()
        await _sweep_hard_expiry()
    except Exception as e:
        logger.warning(f"[GraceSweeper] initial sweep warning: {e}")

    while True:
        try:
            await asyncio.sleep(GRACE_SWEEPER_INTERVAL)
            await _sweep_grace_periods()
            await _sweep_hard_expiry()
        except asyncio.CancelledError:
            logger.info("[GraceSweeper] cancelled — shutting down")
            raise
        except Exception as e:
            # Never let the sweeper crash — log and continue
            logger.error(f"[Sweeper] sweep error: {e}")


async def _sweep_grace_periods() -> None:
    """
    Scan Redis for expired grace periods and close those rooms.
    """
    now = time.time()
    try:
        grace_entries = await room_state.scan_grace_keys()
    except Exception:
        return

    for room_id, grace_until in grace_entries:
        if now >= grace_until:
            await _close_room(room_id, reason="grace_expired")


async def _sweep_hard_expiry() -> None:
    """
    Scan PG for rooms older than 24 hours and close them.
    Also sends a 5-minute warning to rooms approaching the limit.
    """
    try:
        async with db_conn.pool.acquire() as conn:
            # Fetch all active rooms
            rooms = await conn.fetch("SELECT room_id, title, created_at FROM rooms WHERE is_active = TRUE")
            
            now_utc = datetime.now()
            for r in rooms:
                room_id = str(r["room_id"])
                age = now_utc - r["created_at"]
                
                # 1. Hard Expiry (24h)
                if age >= timedelta(hours=24):
                    logger.info(f"[Sweeper] Hard expiry (24h) reached for room={room_id}")
                    await _close_room(room_id, reason="hard_expiry")
                
                # 2. 5-minute Warning (23h 55m)
                elif age >= timedelta(hours=23, minutes=55):
                    # Check if warning already sent
                    warning_key = f"room:{room_id}:expiry_warning_sent"
                    if not await async_redis.get(warning_key): #type: ignore
                        await manager.broadcast(room_id, {
                            "type": MsgType.ROOM_CLOSED, # Or a more specific type if we add it
                            "message": "Notice: This workshop will end in 5 minutes (24h limit reached).",
                            "countdown": 300
                        })
                        await async_redis.set(warning_key, "1", ex=600) #type:ignore # Expire after 10 mins
    except Exception as e:
        logger.error(f"[Sweeper] hard_expiry sweep failed: {e}")


async def _close_room(room_id: str, reason: str) -> None:
    """
    Common closure logic for any reason.
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
    msg = "The host did not reconnect. The room has been closed."
    if reason == "hard_expiry":
        msg = "This workshop has ended after its 24-hour limit."

    try:
        await manager.broadcast(room_id, {
            "type":    MsgType.ROOM_CLOSED,
            "message": msg,
            "reason":  reason
        })
    except Exception as e:
        logger.error(f"[Sweeper] broadcast failed room={room_id}: {e}")

    # ── 5. Expire Redis ────────────────────────────────────────────────────────
    try:
        await room_state.expire_room(room_id)
    except Exception as e:
        logger.error(f"[GraceSweeper] expire_room failed room={room_id}: {e}")

    logger.info(f"[GraceSweeper] room={room_id} closed after grace period expiry")