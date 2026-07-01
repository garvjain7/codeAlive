"""
ot_collab/room_state/presence.py
---------------------------------
Redis operations for user presence in a room.

Redis key managed here:
  room:{room_id}:users    HASH    user_id → JSON{username, color, line, col,
                                                  role, is_muted}

The users hash is the live presence state. It is:
  - Populated at join time, seeded with role + is_muted from PostgreSQL
  - Updated on cursor move (lossy, best-effort)
  - Updated on mute/unmute and role change (must match PG)
  - Removed per-user on disconnect
  - Fully cleared on room teardown

Critical: role and is_muted in this hash are CACHES of PG state.
On cold-start recovery, they must be re-seeded from PG at join time.
The join handler (handlers/joins.py) is responsible for passing the
correct role and is_muted from PG when calling add_user_to_room().
"""

from __future__ import annotations
import json
import logging
from typing import Optional

from core.redis_client import async_redis
from ..models import ParticipantRole, ROOM_TTL_SECONDS

logger = logging.getLogger(__name__)


def _key_users(room_id: str) -> str:
    return f"room:{room_id}:users"


async def add_user_to_room(
    room_id:  str,
    user_id:  str,
    username: str,
    color:    str,
    role:     str = ParticipantRole.PARTICIPANT,
    is_muted: bool = False,
) -> None:
    """
    Add or update a user entry in the room presence hash.

    role and is_muted must be passed in from PG at join time —
    never default them to participant/False without checking PG first.
    The defaults here are a safety fallback only.
    """
    user_data = json.dumps({
        "username": username,
        "color":    color,
        "line":     1,
        "col":      0,
        "role":     role,
        "is_muted": is_muted,
    })
    pipe = async_redis.pipeline()
    pipe.hset(_key_users(room_id), user_id, user_data)
    pipe.expire(_key_users(room_id), ROOM_TTL_SECONDS)
    await pipe.execute()


async def remove_user_from_room(room_id: str, user_id: str) -> None:
    """Remove a single user from the presence hash on disconnect."""
    await async_redis.hdel(_key_users(room_id), user_id) #type:ignore


async def get_user_state(room_id: str, user_id: str) -> Optional[dict]:
    """
    Return the parsed presence entry for a single user.
    Returns None if user not in room — caller handles missing case.
    """
    raw = await async_redis.hget(_key_users(room_id), user_id) #type:ignore
    if raw is None:
        return None
    return json.loads(raw)


async def get_room_users(room_id: str) -> dict[str, dict]:
    """
    Return {user_id: {username, color, line, col, role, is_muted}}
    for all connected users. Empty dict if room has no presence data.
    """
    raw = await async_redis.hgetall(_key_users(room_id)) #type:ignore
    return {uid: json.loads(data) for uid, data in raw.items()}


async def get_existing_colors(room_id: str) -> list[str]:
    """Return colors already assigned in this room for assign_color()."""
    users = await get_room_users(room_id)
    return [u["color"] for u in users.values()]


async def update_user_cursor(
    room_id: str,
    user_id: str,
    line:    int,
    col:     int,
) -> None:
    """
    Update cursor position. Lossy — if user just disconnected, silently ignore.
    Does a read-modify-write on the single hash field. Not transactional
    because cursor position is ephemeral — stale cursor is acceptable.
    """
    raw = await async_redis.hget(_key_users(room_id), user_id) #type:ignore
    if raw is None:
        return
    data = json.loads(raw)
    data["line"] = line
    data["col"]  = col
    await async_redis.hset(_key_users(room_id), user_id, json.dumps(data)) #type:ignore


async def set_user_muted(room_id: str, user_id: str, is_muted: bool) -> None:
    """
    Update mute state in the presence hash.
    Called after PG is updated — Redis reflects the new state immediately.
    """
    raw = await async_redis.hget(_key_users(room_id), user_id) #type:ignore
    if raw is None:
        return
    data = json.loads(raw)
    data["is_muted"] = is_muted
    await async_redis.hset(_key_users(room_id), user_id, json.dumps(data)) #type:ignore


async def set_user_role(room_id: str, user_id: str, role: str) -> None:
    """
    Update role in the presence hash.
    Called after PG is updated — Redis reflects the new role immediately.
    """
    raw = await async_redis.hget(_key_users(room_id), user_id) #type:ignore
    if raw is None:
        return
    data = json.loads(raw)
    data["role"] = role
    await async_redis.hset(_key_users(room_id), user_id, json.dumps(data)) #type:ignore


async def is_user_muted(room_id: str, user_id: str) -> bool:
    """
    Fast mute check for the op hot path.
    Returns False if user not found (graceful degradation).
    """
    state = await get_user_state(room_id, user_id)
    if state is None:
        return False
    return bool(state.get("is_muted", False))


async def get_user_role(room_id: str, user_id: str) -> Optional[str]:
    """Return role string for a user, or None if not found."""
    state = await get_user_state(room_id, user_id)
    if state is None:
        return None
    return state.get("role")


async def expire_presence_key(room_id: str) -> None:
    """Delete the users hash. Called on room teardown."""
    await async_redis.delete(_key_users(room_id))