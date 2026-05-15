"""
ot_collab/connection_manager.py
--------------------------------
In-memory WebSocket connection registry.

Manages the map: room_id → {user_id → WebSocket}

Single instance imported by ws_router.py.
No Redis here — this is process-local state.

Scaling note: on a single Render instance this is sufficient.
When you scale to multiple instances, replace broadcast() with
a Redis pub/sub publisher and add a subscriber task per room.
The interface of this class stays identical — only the internals change.

Thread safety: FastAPI runs on a single asyncio event loop.
All coroutines are cooperative — no true concurrency within one process.
The dict operations here are safe without locks.
"""

from __future__ import annotations
import json
import logging
from typing import Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:

    def __init__(self):
        # rooms: { room_id: { user_id: WebSocket } }
        self._rooms: dict[str, dict[str, WebSocket]] = {}

    # ── Connection lifecycle ───────────────────────────────────────────────────

    def connect(self, room_id: str, user_id: str, websocket: WebSocket) -> None:
        """
        Register a WebSocket connection.
        If same user connects from two tabs, both are tracked separately —
        but we store only one WS per user_id (last one wins).
        This is fine: both tabs will receive broadcasts via the single socket.
        A user connecting from two tabs is an edge case; for presence purposes
        they count as one participant.
        """
        if room_id not in self._rooms:
            self._rooms[room_id] = {}
        self._rooms[room_id][user_id] = websocket
        logger.debug(f"[CM] connected user={user_id} room={room_id} "
                     f"total={len(self._rooms[room_id])}")

    def disconnect(self, room_id: str, user_id: str) -> None:
        """
        Remove a WebSocket connection.
        Safe to call even if user or room not present (reconnect race).
        """
        room = self._rooms.get(room_id)
        if room is None:
            return
        room.pop(user_id, None)
        if not room:
            # Last user left — clean up the room entry
            del self._rooms[room_id]
        logger.debug(f"[CM] disconnected user={user_id} room={room_id}")

    def is_connected(self, room_id: str, user_id: str) -> bool:
        return user_id in self._rooms.get(room_id, {})

    def get_connection_count(self, room_id: str) -> int:
        return len(self._rooms.get(room_id, {}))

    def get_connected_user_ids(self, room_id: str) -> list[str]:
        return list(self._rooms.get(room_id, {}).keys())

    # ── Sending ────────────────────────────────────────────────────────────────

    async def send_to(
        self,
        room_id: str,
        user_id: str,
        message: dict,
    ) -> None:
        """
        Send a message to a specific user in a room.
        Silently drops if user is not connected — they may have disconnected
        between the time we queued the send and now. This is safe: on their
        next reconnect they'll get a fresh snapshot.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return
        ws = room.get(user_id)
        if ws is None:
            return
        try:
            await ws.send_text(json.dumps(message))
        except Exception as e:
            # WebSocket may have closed between is_connected check and send.
            # Log and move on — disconnect() will be called by the endpoint's
            # finally block when the receive loop exits.
            logger.warning(f"[CM] send_to failed user={user_id} room={room_id}: {e}")

    async def broadcast(
        self,
        room_id:         str,
        message:         dict,
        exclude_user_id: Optional[str] = None,
    ) -> None:
        """
        Broadcast a message to all connected users in a room.
        exclude_user_id: skip this user (used to not echo back to sender).

        Sends to all connections concurrently — but since we're on a single
        asyncio loop, it's sequential awaits. Good enough for typical room sizes.
        For large rooms (50+) this could be parallelized with asyncio.gather.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return

        payload = json.dumps(message)
        failed  = []

        for uid, ws in list(room.items()):
            if uid == exclude_user_id:
                continue
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.warning(f"[CM] broadcast failed user={uid} room={room_id}: {e}")
                failed.append(uid)

        # Clean up dead connections found during broadcast
        for uid in failed:
            room.pop(uid, None)

    async def send_to_host(
        self,
        room_id: str,
        host_id: str,
        message: dict,
    ) -> bool:
        """
        Send a message specifically to the host.
        Returns True if host was reachable, False if not connected.
        Used for join_request notifications.
        """
        if not self.is_connected(room_id, host_id):
            return False
        await self.send_to(room_id, host_id, message)
        return True


# ── Module-level singleton ────────────────────────────────────────────────────
# Imported by ws_router.py. One instance per process.

manager = ConnectionManager()