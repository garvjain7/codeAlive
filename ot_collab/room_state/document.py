"""
ot_collab/room_state/document.py
--------------------------------
Redis operations for document content, revision, and operation history.

This is the hot path. Every keystroke from every user goes through
apply_op_to_room(). Keep it fast — no PG calls, minimal Redis round trips.

Redis keys managed here:
  room:{room_id}:doc      STRING  current document content
  room:{room_id}:rev      STRING  current revision (stored as string, cast on read)
  room:{room_id}:history  LIST    serialized {revision, op} JSON entries
"""

from __future__ import annotations
import json
import asyncio
import logging
from typing import Optional

from core.redis_client import async_redis
from ..models import Op, ROOM_TTL_SECONDS
from .. import ot_engine

logger = logging.getLogger(__name__)


def _key_doc(room_id: str)     -> str: return f"room:{room_id}:doc"
def _key_rev(room_id: str)     -> str: return f"room:{room_id}:rev"
def _key_history(room_id: str) -> str: return f"room:{room_id}:history"


async def init_document(
    room_id:  str,
    content:  str,
    revision: int,
) -> None:
    """
    Seed doc, rev, and history keys in Redis.
    Called by room_meta.init_room_in_redis().
    Uses a pipeline — all writes land together.
    """
    pipe = async_redis.pipeline()
    pipe.set(_key_doc(room_id),    content)
    pipe.set(_key_rev(room_id),    str(revision))
    pipe.delete(_key_history(room_id))          # clear stale history on re-seed
    pipe.expire(_key_doc(room_id),     ROOM_TTL_SECONDS)
    pipe.expire(_key_rev(room_id),     ROOM_TTL_SECONDS)
    pipe.expire(_key_history(room_id), ROOM_TTL_SECONDS)
    await pipe.execute()


async def get_room_doc(room_id: str) -> tuple[str, int]:
    """
    Returns (content, revision).
    Raises KeyError if room not in Redis — caller should trigger cold recovery.
    """
    pipe = async_redis.pipeline()
    pipe.get(_key_doc(room_id))
    pipe.get(_key_rev(room_id))
    results = await pipe.execute()

    content  = results[0]
    revision = results[1]

    if content is None or revision is None:
        raise KeyError(f"Room {room_id} not in Redis")

    return content, int(revision)


async def room_exists_in_redis(room_id: str) -> bool:
    """Check if room document is live in Redis."""
    return await async_redis.exists(_key_doc(room_id)) == 1


async def get_history_since(room_id: str, since_revision: int) -> list[Op]:
    """
    Return ops from Redis history that occurred after since_revision.

    The history list stores {revision, op} entries. We filter by
    revision > since_revision and return the Op objects in order.

    Performance: LRANGE fetches the whole list. Mitigated by periodic
    snapshots every SNAPSHOT_EVERY_N_OPS — list stays short.
    """
    raw_ops = await async_redis.lrange(_key_history(room_id), 0, -1) #type:ignore
    result  = []
    for raw in raw_ops:
        entry = json.loads(raw)
        if entry["revision"] > since_revision:
            result.append(Op.from_dict(entry["op"]))
    return result


async def apply_op_to_room(
    room_id:     str,
    op:          Op,
    max_retries: int = 5,
) -> tuple[Op, int]:
    """
    Atomically apply op to the room document using WATCH/MULTI/EXEC.

    Returns (op, new_revision).
    Raises KeyError if room disappears mid-operation.
    Raises RuntimeError if all retries exhausted (extreme contention).

    The op passed in must already be transformed against concurrent history
    (done in handlers/ops.py before calling here). This function only
    applies — it does not transform.
    """
    for attempt in range(max_retries):
        await async_redis.watch(_key_rev(room_id))

        try:
            rev_str = await async_redis.get(_key_rev(room_id))
            doc     = await async_redis.get(_key_doc(room_id))

            if rev_str is None or doc is None:
                await async_redis.unwatch()
                raise KeyError(f"Room {room_id} disappeared from Redis mid-operation")

            current_rev = int(rev_str)
            new_rev     = current_rev + 1

            new_doc = ot_engine.apply(doc, op)

            history_entry = json.dumps({
                "revision": new_rev,
                "op":       op.to_dict(),
            })

            pipe = async_redis.pipeline(transaction=True)
            pipe.set(_key_doc(room_id),       new_doc)
            pipe.set(_key_rev(room_id),       str(new_rev))
            pipe.rpush(_key_history(room_id), history_entry)
            pipe.expire(_key_doc(room_id),     ROOM_TTL_SECONDS)
            pipe.expire(_key_rev(room_id),     ROOM_TTL_SECONDS)
            pipe.expire(_key_history(room_id), ROOM_TTL_SECONDS)

            results = await pipe.execute()

            if results is None:
                # WATCH conflict — another op landed concurrently.
                # Caller will re-fetch history and re-transform on retry loop.
                await asyncio.sleep(0.005 * (attempt + 1))
                continue

            return op, new_rev

        except (KeyError, RuntimeError):
            await async_redis.unwatch()
            raise
        except Exception:
            await async_redis.unwatch()
            raise

    raise RuntimeError(
        f"apply_op_to_room: all {max_retries} retries exhausted "
        f"for room {room_id}. Extreme write contention."
    )


async def expire_document_keys(room_id: str) -> None:
    """Delete doc, rev, history keys. Called on room teardown."""
    pipe = async_redis.pipeline()
    pipe.delete(_key_doc(room_id))
    pipe.delete(_key_rev(room_id))
    pipe.delete(_key_history(room_id))
    await pipe.execute()