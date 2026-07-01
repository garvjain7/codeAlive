"""
ot_collab/room_service.py
--------------------------
Business logic layer. Coordinates Redis + PostgreSQL for operations
that must update both stores atomically from the caller's perspective.

Every function here:
  1. Validates permissions (via permissions.py)
  2. Updates PostgreSQL (durable authority)
  3. Updates Redis (live cache)
  4. Returns data needed for broadcast — does NOT broadcast itself

Broadcast is the caller's responsibility (handlers/*.py).
This keeps room_service testable without a WebSocket context.

Rule: if an operation touches both PG and Redis, it belongs here.
      If it touches only Redis (cursor update), it belongs in room_state.
      If it touches only PG (snapshot save), it belongs in db/operations.
"""

from __future__ import annotations
import logging
from typing import Optional

import db.connection as db_conn
from . import permissions
from . import room_state
from .db import rooms as db_rooms
from .password_utils import hash_password

logger = logging.getLogger(__name__)


# ── Mute / Unmute ─────────────────────────────────────────────────────────────

async def mute_user(
    room_id:        str,
    actor_role:     str,
    target_user_id: str,
) -> None:
    """
    Mute a participant. Updates PG then Redis.
    Raises PermissionError if actor lacks mute authority.
    Raises ValueError if target is not in the room.
    """
    permissions.assert_elevated(actor_role, "mute_user")

    async with db_conn.pool.acquire() as conn:
        await db_rooms.set_participant_muted(conn, room_id, target_user_id, True)

    await room_state.set_user_muted(room_id, target_user_id, True)


async def unmute_user(
    room_id:        str,
    actor_role:     str,
    target_user_id: str,
) -> None:
    """Unmute a participant. Updates PG then Redis."""
    permissions.assert_elevated(actor_role, "unmute_user")

    async with db_conn.pool.acquire() as conn:
        await db_rooms.set_participant_muted(conn, room_id, target_user_id, False)

    await room_state.set_user_muted(room_id, target_user_id, False)


# ── Kick ──────────────────────────────────────────────────────────────────────

async def kick_user(
    room_id:        str,
    actor_role:     str,
    target_user_id: str,
) -> None:
    """
    Kick a participant.
      - Removes from PG room_participants (they must re-request to join)
      - Removes from Redis presence
      - Revokes auth cache (prevents immediate password-bypass rejoin)

    Does NOT close the target's WebSocket — the caller (handler) does that
    by sending YOU_WERE_KICKED and then disconnecting.
    """
    permissions.assert_elevated(actor_role, "kick_user")

    async with db_conn.pool.acquire() as conn:
        await db_rooms.remove_participant(conn, room_id, target_user_id)

    await room_state.remove_user_from_room(room_id, target_user_id)
    await room_state.revoke_room_auth(room_id, target_user_id)


# ── Promote / Demote cohost ───────────────────────────────────────────────────

async def promote_cohost(
    room_id:        str,
    actor_role:     str,
    target_user_id: str,
) -> None:
    """
    Promote a participant to cohost.
    Only the host can do this. Only one cohost at a time — promoting a new
    one implicitly demotes the old one (handled at DB level via cohost_id).
    """
    permissions.assert_host(actor_role, "promote_cohost")

    async with db_conn.pool.acquire() as conn:
        # If there's an existing cohost, demote them first
        existing_cohost = await conn.fetchval("""
            SELECT cohost_id FROM rooms WHERE room_id = $1
        """, __import__('uuid').UUID(room_id))

        if existing_cohost:
            await db_rooms.clear_cohost(conn, room_id, str(existing_cohost))
            await room_state.set_user_role(room_id, str(existing_cohost), "participant")

        await db_rooms.set_cohost(conn, room_id, target_user_id)

    await room_state.set_user_role(room_id, target_user_id, "cohost")
    await room_state.set_room_cohost(room_id, target_user_id)


async def demote_cohost(
    room_id:        str,
    actor_role:     str,
    target_user_id: str,
) -> None:
    """Demote the cohost back to participant."""
    permissions.assert_host(actor_role, "demote_cohost")

    async with db_conn.pool.acquire() as conn:
        await db_rooms.clear_cohost(conn, room_id, target_user_id)

    await room_state.set_user_role(room_id, target_user_id, "participant")
    await room_state.clear_room_cohost(room_id)


# ── Lock / Unlock room ────────────────────────────────────────────────────────

async def lock_room(room_id: str, actor_role: str) -> None:
    """Lock the room — no new joins accepted."""
    permissions.assert_elevated(actor_role, "lock_room")

    async with db_conn.pool.acquire() as conn:
        await db_rooms.set_room_locked(conn, room_id, True)

    await room_state.set_room_locked(room_id, True)


async def unlock_room(room_id: str, actor_role: str) -> None:
    """Unlock the room — new joins accepted again."""
    permissions.assert_elevated(actor_role, "unlock_room")

    async with db_conn.pool.acquire() as conn:
        await db_rooms.set_room_locked(conn, room_id, False)

    await room_state.set_room_locked(room_id, False)


# ── Password ──────────────────────────────────────────────────────────────────

async def set_password(
    room_id:    str,
    actor_role: str,
    plaintext:  Optional[str],   # None = clear password
) -> int:
    """
    Set or clear the room password.
    Hashes the plaintext, updates PG, increments password_version in Redis.
    Returns the new password_version so caller can broadcast it.

    Incrementing password_version invalidates all existing auth cache entries
    without needing to enumerate or delete them explicitly.
    """
    permissions.assert_host(actor_role, "set_password")

    password_hash = hash_password(plaintext) if plaintext else None

    async with db_conn.pool.acquire() as conn:
        new_version = await db_rooms.set_room_password(conn, room_id, password_hash)

    # Sync the new version to Redis so auth_cache checks use the latest value
    await room_state.set_password_version(room_id, new_version)

    return new_version


# ── Host disconnect / reconnect ───────────────────────────────────────────────

async def handle_host_disconnect(room_id: str) -> float:
    """
    Called when host's WebSocket closes unexpectedly (not via close_room message).
    Saves a snapshot and starts the grace period.
    Returns the grace expiry timestamp for broadcast.
    """
    # Save snapshot immediately for durability
    try:
        content, revision = await room_state.get_room_doc(room_id)
        async with db_conn.pool.acquire() as conn:
            from .db import operations as db_ops
            await db_ops.save_snapshot(conn, room_id, content, revision)
            await db_rooms.update_room_revision(conn, room_id, revision)
    except Exception as e:
        logger.warning(f"[RoomService] host disconnect snapshot failed room={room_id}: {e}")

    grace_until = await room_state.set_host_grace(room_id)
    return grace_until


async def handle_host_rejoin(room_id: str) -> None:
    """
    Called when host reconnects within the grace period.
    Clears the grace timer so the sweeper doesn't close the room.
    """
    await room_state.clear_host_grace(room_id)


# ── Room close ────────────────────────────────────────────────────────────────

async def close_room(room_id: str, actor_role: str) -> tuple[str, int]:
    """
    Permanently close the room.
    Saves final snapshot, marks PG inactive, returns (content, revision)
    so caller can include them in any final broadcast if needed.
    Caller is responsible for expiring Redis keys and disconnecting clients.
    """
    permissions.assert_host(actor_role, "close_room")

    try:
        content, revision = await room_state.get_room_doc(room_id)
    except KeyError:
        content, revision = "", 0

    async with db_conn.pool.acquire() as conn:
        from .db import operations as db_ops
        if content:
            await db_ops.save_snapshot(conn, room_id, content, revision)
        await db_rooms.update_room_revision(conn, room_id, revision)
        await db_rooms.set_room_inactive(conn, room_id)

    return content, revision