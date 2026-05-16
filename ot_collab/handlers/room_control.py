"""
ot_collab/handlers/room_control.py
------------------------------------
Handles room-level control actions:
  lock_room, unlock_room, set_password, close_room

These are structural operations that change room state visible to
all participants. Every action here broadcasts a room-level event
after the state change is persisted.
"""

from __future__ import annotations
import json
import logging

from fastapi import WebSocket, BackgroundTasks

from ..models import MsgType, SetPasswordMessage
from .. import room_state, room_service
from ..connection_manager import manager

logger = logging.getLogger(__name__)


async def handle_lock_room(
    websocket:  WebSocket,
    room_id:    str,
    actor_id:   str,
) -> None:
    """
    Lock the room — no new joins accepted until unlocked.
    Existing participants are unaffected.
    """
    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        await room_service.lock_room(room_id, actor_role)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[RoomControl] lock_room failed room={room_id}: {e}")
        await _send_error(websocket, "server_error", "Lock failed. Please try again.")
        return

    await manager.broadcast(room_id, {
        "type":      MsgType.ROOM_LOCKED,
        "locked_by": actor_id,
    })

    logger.info(f"[RoomControl] room={room_id} locked by actor={actor_id}")


async def handle_unlock_room(
    websocket: WebSocket,
    room_id:   str,
    actor_id:  str,
) -> None:
    """Unlock the room — new joins accepted again."""
    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        await room_service.unlock_room(room_id, actor_role)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[RoomControl] unlock_room failed room={room_id}: {e}")
        await _send_error(websocket, "server_error", "Unlock failed. Please try again.")
        return

    await manager.broadcast(room_id, {
        "type": MsgType.ROOM_UNLOCKED,
    })

    logger.info(f"[RoomControl] room={room_id} unlocked by actor={actor_id}")


async def handle_set_password(
    websocket: WebSocket,
    msg:       dict,
    room_id:   str,
    actor_id:  str,
) -> None:
    """
    Set or clear the room password.

    password = None → remove password protection
    password = str  → set new password (bcrypt hashed in room_service)

    After setting, PASSWORD_CHANGED is broadcast so connected clients
    know their auth cache is now stale. On next reconnect they will
    be prompted for the new password.
    Currently connected users are NOT re-prompted mid-session.
    """
    try:
        parsed = SetPasswordMessage.from_dict(msg)
    except (KeyError, TypeError) as e:
        await _send_error(websocket, "invalid_message", f"Malformed set_password message: {e}")
        return

    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        new_version = await room_service.set_password(room_id, actor_role, parsed.password)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[RoomControl] set_password failed room={room_id}: {e}")
        await _send_error(websocket, "server_error", "Password change failed. Please try again.")
        return

    has_password = parsed.password is not None

    # Broadcast so clients know the password state changed.
    # new_version lets clients invalidate their local auth cache.
    await manager.broadcast(room_id, {
        "type":             MsgType.PASSWORD_CHANGED,
        "has_password":     has_password,
        "password_version": new_version,
    })

    action = "set" if has_password else "cleared"
    logger.info(f"[RoomControl] room={room_id} password {action} by actor={actor_id}")


async def handle_close_room(
    websocket:   WebSocket,
    room_id:     str,
    actor_id:    str,
    background:  BackgroundTasks,
) -> None:
    """
    Host permanently closes the room.

    Sequence:
      1. room_service saves final snapshot + marks PG inactive
      2. Broadcast ROOM_CLOSED to all connected clients
      3. Expire all Redis keys
      4. Return — ws_router relay loop breaks after calling this

    The caller (ws_router) is responsible for breaking out of the
    relay loop so the host's own connection cleans up via finally block.
    """
    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        await room_service.close_room(room_id, actor_role)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[RoomControl] close_room failed room={room_id}: {e}")
        # Even if snapshot fails, still close the room
        pass

    await manager.broadcast(room_id, {
        "type": MsgType.ROOM_CLOSED,
    })

    await room_state.expire_room(room_id)

    logger.info(f"[RoomControl] room={room_id} closed by actor={actor_id}")


# ── Shared error helper ────────────────────────────────────────────────────────

async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    try:
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    code,
            "message": message,
        }))
    except Exception:
        pass