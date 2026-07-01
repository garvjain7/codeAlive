"""
ot_collab/room_state/auth_cache.py
------------------------------------
Redis cache for room password authorization.

Redis key managed here:
  room:{room_id}:auth:{user_id}   STRING  JSON{expires_at, password_version}

Design:
  Once a user correctly enters a room password, we cache their authorization
  in Redis. On subsequent reconnects (refresh, disconnect/rejoin), we check
  this cache instead of prompting for the password again.

  The cache entry carries password_version — the version of the room password
  at the time of authorization. If the host changes the password, the room's
  password_version is incremented (room_meta.increment_password_version()),
  and all existing cache entries become stale because their stored version
  no longer matches. This is the invalidation mechanism — no explicit purge
  needed.

  TTL is set to min(time until expires_at, ROOM_TTL_SECONDS) so entries
  never outlive the room.

Intentionally NOT persisted to PostgreSQL:
  Auth cache is ephemeral by design. If Redis restarts, users re-enter their
  password once. This is acceptable — the alternative (PG persistence) adds
  complexity for a UX convenience feature.
"""

from __future__ import annotations
import json
import time
import logging
from typing import Optional

from core.redis_client import async_redis
from ..models import ROOM_TTL_SECONDS

logger = logging.getLogger(__name__)

# Hard cap on auth cache lifetime — even if room TTL is longer
AUTH_CACHE_MAX_SECONDS = 86400  # 24 hours


def _key_auth(room_id: str, user_id: str) -> str:
    return f"room:{room_id}:auth:{user_id}"


async def set_room_auth(
    room_id:          str,
    user_id:          str,
    password_version: int,
) -> None:
    """
    Cache successful password authorization for a user.

    expires_at is set to now + 24h (hard cap) or room TTL, whichever is less.
    password_version is stored so we can detect stale entries after password change.
    """
    now        = time.time()
    expires_at = now + min(AUTH_CACHE_MAX_SECONDS, ROOM_TTL_SECONDS)
    ttl_secs   = int(expires_at - now)

    payload = json.dumps({
        "expires_at":       expires_at,
        "password_version": password_version,
    })

    await async_redis.setex(_key_auth(room_id, user_id), ttl_secs, payload)


async def get_room_auth(
    room_id:                  str,
    user_id:                  str,
    current_password_version: int,
) -> bool:
    """
    Check if a user has valid cached authorization for this room.

    Returns True only if:
      1. Cache entry exists
      2. Entry has not expired (expires_at > now)
      3. password_version matches current room password version

    Returns False in all other cases — caller will prompt for password.
    """
    raw = await async_redis.get(_key_auth(room_id, user_id))
    if raw is None:
        return False

    try:
        entry = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[AuthCache] corrupt entry room={room_id} user={user_id}")
        return False

    # Check expiry
    if time.time() > entry.get("expires_at", 0):
        return False

    # Check password version — stale if host changed password since auth
    if entry.get("password_version") != current_password_version:
        return False

    return True


async def revoke_room_auth(room_id: str, user_id: str) -> None:
    """
    Explicitly revoke a user's cached auth.
    Called when a user is kicked — prevents immediate rejoin with cached auth.
    """
    await async_redis.delete(_key_auth(room_id, user_id))


async def expire_all_auth_keys(room_id: str, user_ids: list[str]) -> None:
    """
    Clear auth cache for all known users in a room.
    Called on room close — not strictly necessary (entries will TTL out)
    but good hygiene.
    """
    if not user_ids:
        return
    keys = [_key_auth(room_id, uid) for uid in user_ids]
    await async_redis.delete(*keys)