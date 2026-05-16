"""
ot_collab/room_state/room_meta.py
----------------------------------
Redis operations for room-level metadata.

Redis keys managed here:
  room:{room_id}:host             STRING  host user_id
  room:{room_id}:cohost           STRING  cohost user_id (absent if none)
  room:{room_id}:locked           STRING  "1" if locked, absent if not
  room:{room_id}:password_version STRING  int, incremented on password change
  room:{room_id}:host_grace_until STRING  Unix timestamp float, absent if no grace

On cold-start recovery:
  host and cohost are re-seeded from PG (via ws_router._ensure_room_in_redis).
  locked and password_version are also re-seeded from PG rooms row.
  host_grace_until is ephemeral — if the server crashes during a grace period,
  the grace sweeper picks it up via Redis on restart.
"""

from __future__ import annotations
import time
import logging
from typing import Optional

from core.redis_client import async_redis
from ..models import ROOM_TTL_SECONDS, GRACE_PERIOD_SECONDS

logger = logging.getLogger(__name__)


def _key_host(room_id: str)             -> str: return f"room:{room_id}:host"
def _key_cohost(room_id: str)           -> str: return f"room:{room_id}:cohost"
def _key_locked(room_id: str)           -> str: return f"room:{room_id}:locked"
def _key_password_version(room_id: str) -> str: return f"room:{room_id}:password_version"
def _key_grace(room_id: str)            -> str: return f"room:{room_id}:host_grace_until"


async def init_room_meta(
    room_id:          str,
    host_id:          str,
    cohost_id:        Optional[str],
    is_locked:        bool,
    password_version: int,
) -> None:
    """
    Seed room metadata keys in Redis.
    Called by init_room_in_redis() during room creation and cold-start recovery.
    """
    pipe = async_redis.pipeline()
    pipe.set(_key_host(room_id), host_id)
    pipe.expire(_key_host(room_id), ROOM_TTL_SECONDS)

    if cohost_id:
        pipe.set(_key_cohost(room_id), cohost_id)
        pipe.expire(_key_cohost(room_id), ROOM_TTL_SECONDS)
    else:
        pipe.delete(_key_cohost(room_id))

    if is_locked:
        pipe.set(_key_locked(room_id), "1")
        pipe.expire(_key_locked(room_id), ROOM_TTL_SECONDS)
    else:
        pipe.delete(_key_locked(room_id))

    pipe.set(_key_password_version(room_id), str(password_version))
    pipe.expire(_key_password_version(room_id), ROOM_TTL_SECONDS)

    await pipe.execute()


# ── Host ──────────────────────────────────────────────────────────────────────

async def get_room_host(room_id: str) -> Optional[str]:
    return await async_redis.get(_key_host(room_id))


async def set_room_host(room_id: str, host_id: str) -> None:
    pipe = async_redis.pipeline()
    pipe.set(_key_host(room_id), host_id)
    pipe.expire(_key_host(room_id), ROOM_TTL_SECONDS)
    await pipe.execute()


# ── Cohost ────────────────────────────────────────────────────────────────────

async def get_room_cohost(room_id: str) -> Optional[str]:
    return await async_redis.get(_key_cohost(room_id))


async def set_room_cohost(room_id: str, cohost_id: str) -> None:
    pipe = async_redis.pipeline()
    pipe.set(_key_cohost(room_id), cohost_id)
    pipe.expire(_key_cohost(room_id), ROOM_TTL_SECONDS)
    await pipe.execute()


async def clear_room_cohost(room_id: str) -> None:
    await async_redis.delete(_key_cohost(room_id))


# ── Room lock ─────────────────────────────────────────────────────────────────

async def is_room_locked(room_id: str) -> bool:
    val = await async_redis.get(_key_locked(room_id))
    return val == "1"


async def set_room_locked(room_id: str, locked: bool) -> None:
    pipe = async_redis.pipeline()
    if locked:
        pipe.set(_key_locked(room_id), "1")
        pipe.expire(_key_locked(room_id), ROOM_TTL_SECONDS)
    else:
        pipe.delete(_key_locked(room_id))
    await pipe.execute()


# ── Password version ──────────────────────────────────────────────────────────

async def get_password_version(room_id: str) -> int:
    val = await async_redis.get(_key_password_version(room_id))
    return int(val) if val is not None else 0


async def increment_password_version(room_id: str) -> int:
    """
    Atomically increment the password version counter.
    Returns the new version.
    All existing auth cache entries (room:{room_id}:auth:{user_id}) become
    invalid — they carry the old version and will fail the version check
    in auth_cache.get_room_auth().
    """
    new_version = await async_redis.incr(_key_password_version(room_id))
    await async_redis.expire(_key_password_version(room_id), ROOM_TTL_SECONDS)
    return new_version


async def set_password_version(room_id: str, version: int) -> None:
    """Used during cold-start re-seed from PG."""
    pipe = async_redis.pipeline()
    pipe.set(_key_password_version(room_id), str(version))
    pipe.expire(_key_password_version(room_id), ROOM_TTL_SECONDS)
    await pipe.execute()


# ── Grace period ──────────────────────────────────────────────────────────────

async def set_host_grace(room_id: str) -> float:
    """
    Record that the host disconnected and set the grace deadline.
    Stores Unix timestamp of when the grace period expires.
    Returns the expiry timestamp.

    TTL on the key is set to GRACE_PERIOD_SECONDS + 60 (buffer).
    The sweeper is the actual enforcement mechanism — the key TTL
    is just a cleanup safety net.
    """
    until = time.time() + GRACE_PERIOD_SECONDS
    pipe = async_redis.pipeline()
    pipe.set(_key_grace(room_id), str(until))
    pipe.expire(_key_grace(room_id), GRACE_PERIOD_SECONDS + 60)
    await pipe.execute()
    return until


async def get_host_grace(room_id: str) -> Optional[float]:
    """
    Return the grace period expiry timestamp, or None if no grace period.
    None means either no grace period is active, or it already expired
    and the sweeper cleaned it up.
    """
    val = await async_redis.get(_key_grace(room_id))
    return float(val) if val is not None else None


async def clear_host_grace(room_id: str) -> None:
    """Called when host rejoins within the grace period."""
    await async_redis.delete(_key_grace(room_id))


async def scan_grace_keys() -> list[tuple[str, float]]:
    """
    Scan Redis for all active grace period keys.
    Returns list of (room_id, expiry_timestamp) for all rooms
    currently in a host grace period.

    Used by grace_sweeper.py on startup and periodic sweeps.
    SCAN is non-blocking — safe on production Redis.
    """
    results = []
    pattern = "room:*:host_grace_until"
    cursor = 0
    while True:
        cursor, keys = await async_redis.scan(cursor, match=pattern, count=100)
        for key in keys:
            val = await async_redis.get(key)
            if val is not None:
                # Extract room_id from "room:{room_id}:host_grace_until"
                parts   = key.split(":")
                room_id = parts[1] if len(parts) >= 3 else None
                if room_id:
                    results.append((room_id, float(val)))
        if cursor == 0:
            break
    return results


# ── Full room init / teardown ─────────────────────────────────────────────────

async def expire_meta_keys(room_id: str) -> None:
    """Delete all meta keys. Called on room teardown alongside document/presence cleanup."""
    pipe = async_redis.pipeline()
    pipe.delete(_key_host(room_id))
    pipe.delete(_key_cohost(room_id))
    pipe.delete(_key_locked(room_id))
    pipe.delete(_key_password_version(room_id))
    pipe.delete(_key_grace(room_id))
    await pipe.execute()