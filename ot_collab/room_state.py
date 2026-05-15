"""
ot_collab/room_state.py
-----------------------
All Redis reads and writes for live room state.

Redis keys (all prefixed room: — no collision with session: keys):
  room:{room_id}:doc      STRING  current document content
  room:{room_id}:rev      STRING  current revision integer (stored as string,
                                  cast to int on read — decode_responses=True)
  room:{room_id}:history  LIST    serialized Op JSON, index 0 = first op ever
                                  op at index i has revision (base_revision + i + 1)
  room:{room_id}:users    HASH    user_id → JSON{username, color, line, col}
  room:{room_id}:host     STRING  host user_id

TTL: ROOM_TTL_SECONDS (24h) refreshed on every op.

The critical function is apply_op_to_room() which uses a Redis
optimistic lock (WATCH/MULTI/EXEC) to atomically:
  1. Read current doc + rev
  2. Transform op on Python side
  3. Apply op to doc
  4. Write new doc + rev + append to history

This is the equivalent of a database's serializable write.
Without this lock, two concurrent ops from different users can
both read revision 7, both compute revision 8, and one silently
overwrites the other.
"""

from __future__ import annotations
import json
import asyncio
from typing import Optional

from redis_client import async_redis
from .models import Op, ROOM_TTL_SECONDS
from . import ot_engine


# ── Key helpers ───────────────────────────────────────────────────────────────

def _key_doc(room_id: str)     -> str: return f"room:{room_id}:doc"
def _key_rev(room_id: str)     -> str: return f"room:{room_id}:rev"
def _key_history(room_id: str) -> str: return f"room:{room_id}:history"
def _key_users(room_id: str)   -> str: return f"room:{room_id}:users"
def _key_host(room_id: str)    -> str: return f"room:{room_id}:host"


# ── Room initialization ───────────────────────────────────────────────────────

async def init_room_in_redis(
    room_id:  str,
    content:  str,
    revision: int,
    host_id:  str,
) -> None:
    """
    Seed Redis with the initial room state.
    Called when a room is first created, or when it's loaded from
    PostgreSQL snapshot after a Redis cold-start (server restart).

    Uses a pipeline (non-transactional) — all writes succeed or we
    get an exception. If interrupted, the caller retries.
    """
    pipe = async_redis.pipeline()
    pipe.set(_key_doc(room_id), content)
    pipe.set(_key_rev(room_id), str(revision))
    pipe.delete(_key_history(room_id))   # clear any stale history
    pipe.set(_key_host(room_id), host_id)
    # Set TTL on all keys
    pipe.expire(_key_doc(room_id),     ROOM_TTL_SECONDS)
    pipe.expire(_key_rev(room_id),     ROOM_TTL_SECONDS)
    pipe.expire(_key_history(room_id), ROOM_TTL_SECONDS)
    pipe.expire(_key_host(room_id),    ROOM_TTL_SECONDS)
    await pipe.execute()


async def room_exists_in_redis(room_id: str) -> bool:
    """Check if room is live in Redis (not cold)."""
    return await async_redis.exists(_key_doc(room_id)) == 1


# ── Document reads ────────────────────────────────────────────────────────────

async def get_room_doc(room_id: str) -> tuple[str, int]:
    """
    Returns (content, revision).
    Raises KeyError if room not in Redis — caller should load from PG.
    """
    pipe = async_redis.pipeline()
    pipe.get(_key_doc(room_id))
    pipe.get(_key_rev(room_id))
    results = await pipe.execute()

    content  = results[0]
    revision = results[1]

    if content is None or revision is None:
        raise KeyError(f"Room {room_id} not found in Redis")

    return content, int(revision)


async def get_history_since(room_id: str, since_revision: int) -> list[Op]:
    """
    Return ops from Redis history list that occurred after since_revision.

    The history list is append-only. Index 0 = revision (base+1).
    If room was seeded at revision R (from snapshot), history[0] = op at R+1.

    We store base_revision alongside the list so we can compute offsets.
    Actually simpler: we store the revision of each op in the JSON.
    We filter by revision > since_revision.

    Performance: LRANGE gets the whole list. For large rooms this could
    be slow — mitigated by snapshotting every 50 ops, keeping list short.
    """
    raw_ops = await async_redis.lrange(_key_history(room_id), 0, -1)  # type: ignore
    result = []
    for raw in raw_ops:
        entry = json.loads(raw)
        if entry["revision"] > since_revision:
            result.append(Op.from_dict(entry["op"]))
    return result


# ── The atomic op application ─────────────────────────────────────────────────

async def apply_op_to_room(
    room_id: str,
    op:      Op,
    max_retries: int = 5,
) -> tuple[Op, int]:
    """
    Atomically apply op to the room document.

    Uses Redis WATCH/MULTI/EXEC optimistic locking:
      WATCH the revision key
      GET current doc + rev
      Transform op against any concurrent ops if needed (handled by caller)
      Apply op to doc
      MULTI
        SET doc
        SET rev
        RPUSH history
        EXPIRE all keys
      EXEC → None if another client changed rev between WATCH and EXEC

    Returns (transformed_op, new_revision).
    The transformed_op is what was actually applied — may differ from
    the input op if a race occurred and a retry was needed.

    Retries up to max_retries times on optimistic lock conflict.
    Raises RuntimeError if all retries exhausted (should be extremely rare
    under normal load — indicates a thundering herd scenario).

    Database analogy:
      WATCH    = SELECT FOR UPDATE (take optimistic lock)
      MULTI    = BEGIN TRANSACTION
      EXEC     = COMMIT (fails if watched key changed — like serialization failure)
      retry    = rollback and retry (like a retrying serializable transaction)
    """
    for attempt in range(max_retries):
        # WATCH the revision key — if it changes before EXEC, transaction fails
        await async_redis.watch(_key_rev(room_id))

        try:
            rev_str  = await async_redis.get(_key_rev(room_id))
            doc      = await async_redis.get(_key_doc(room_id))

            if rev_str is None or doc is None:
                await async_redis.unwatch()
                raise KeyError(f"Room {room_id} disappeared from Redis mid-operation")

            current_rev = int(rev_str)
            new_rev     = current_rev + 1

            # Apply op to document
            new_doc = ot_engine.apply(doc, op)

            # Build history entry
            history_entry = json.dumps({
                "revision": new_rev,
                "op":       op.to_dict(),
            })

            # Atomic write block
            pipe = async_redis.pipeline(transaction=True)
            pipe.set(_key_doc(room_id),     new_doc)
            pipe.set(_key_rev(room_id),     str(new_rev))
            pipe.rpush(_key_history(room_id), history_entry)
            # Refresh TTL on every op — room stays alive while active
            pipe.expire(_key_doc(room_id),     ROOM_TTL_SECONDS)
            pipe.expire(_key_rev(room_id),     ROOM_TTL_SECONDS)
            pipe.expire(_key_history(room_id), ROOM_TTL_SECONDS)

            results = await pipe.execute()

            # EXEC returns None if WATCH detected a change
            if results is None:
                # Optimistic lock conflict — another op landed between our
                # WATCH and EXEC. We need to re-read and retry.
                # The caller (ws_router) will have already transformed op
                # against known history. The new concurrent op is in history
                # now, so on retry we'll re-read and the caller transforms again.
                await asyncio.sleep(0.005 * (attempt + 1))  # tiny backoff
                continue

            return op, new_rev

        except Exception:
            await async_redis.unwatch()
            raise

    raise RuntimeError(
        f"apply_op_to_room: all {max_retries} retries exhausted for room {room_id}. "
        f"This indicates extreme write contention."
    )


# ── User presence ─────────────────────────────────────────────────────────────

async def add_user_to_room(
    room_id:  str,
    user_id:  str,
    username: str,
    color:    str,
) -> None:
    """Add user to the room's presence hash."""
    user_data = json.dumps({
        "username": username,
        "color":    color,
        "line":     1,
        "col":      0,
    })
    pipe = async_redis.pipeline()
    pipe.hset(_key_users(room_id), user_id, user_data)
    pipe.expire(_key_users(room_id), ROOM_TTL_SECONDS)
    await pipe.execute()


async def remove_user_from_room(room_id: str, user_id: str) -> None:
    """Remove user from room presence hash."""
    await async_redis.hdel(_key_users(room_id), user_id)  # type: ignore


async def update_user_cursor(
    room_id: str,
    user_id: str,
    line:    int,
    col:     int,
) -> None:
    """Update cursor position for a user. Lossy — best effort."""
    raw = await async_redis.hget(_key_users(room_id), user_id)  # type: ignore
    if raw is None:
        return  # user not in room, silently ignore
    data = json.loads(raw)
    data["line"] = line
    data["col"]  = col
    await async_redis.hset(_key_users(room_id), user_id, json.dumps(data))  # type: ignore


async def get_room_users(room_id: str) -> dict[str, dict]:
    """
    Returns {user_id: {username, color, line, col}} for all users in room.
    Empty dict if no users.
    """
    raw = await async_redis.hgetall(_key_users(room_id))  # type: ignore
    return {uid: json.loads(data) for uid, data in raw.items()}


async def get_existing_colors(room_id: str) -> list[str]:
    """Return list of colors already assigned in this room."""
    users = await get_room_users(room_id)
    return [u["color"] for u in users.values()]


# ── Host tracking ─────────────────────────────────────────────────────────────

async def set_room_host(room_id: str, host_id: str) -> None:
    pipe = async_redis.pipeline()
    pipe.set(_key_host(room_id), host_id)
    pipe.expire(_key_host(room_id), ROOM_TTL_SECONDS)
    await pipe.execute()


async def get_room_host(room_id: str) -> Optional[str]:
    return await async_redis.get(_key_host(room_id))


# ── Room teardown ─────────────────────────────────────────────────────────────

async def expire_room(room_id: str) -> None:
    """
    Immediately expire all room keys.
    Called when last user leaves or host closes the room.
    PostgreSQL is the durable store — this just frees Redis memory.
    """
    pipe = async_redis.pipeline()
    pipe.delete(_key_doc(room_id))
    pipe.delete(_key_rev(room_id))
    pipe.delete(_key_history(room_id))
    pipe.delete(_key_users(room_id))
    pipe.delete(_key_host(room_id))
    await pipe.execute()