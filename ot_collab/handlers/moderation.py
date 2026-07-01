"""
ot_collab/handlers/moderation.py
---------------------------------
Handles all participant moderation actions:
  kick, mute, unmute, promote_cohost, demote_cohost

Pattern for every handler:
  1. Parse message
  2. Get actor's role from Redis (fast, no PG)
  3. Delegate to room_service (PG + Redis update)
  4. Send targeted message to the affected user
  5. Broadcast state change to the whole room

room_service raises PermissionError on unauthorized actions —
we catch it here and send an error back to the actor.
"""

from __future__ import annotations
import json
import logging

from fastapi import WebSocket

from ..models import MsgType, TargetUserMessage
from .. import room_state, room_service
from ..connection_manager import manager

logger = logging.getLogger(__name__)


async def handle_kick(
    websocket: WebSocket,
    msg:       dict,
    room_id:   str,
    actor_id:  str,
) -> None:
    """
    Kick a participant out of the room.

    After room_service.kick_user() removes them from PG + Redis:
      - Send YOU_WERE_KICKED to the target (they see a message and disconnect)
      - Broadcast PARTICIPANT_KICKED to the room (others see them leave)

    The target's WebSocket is not forcibly closed here — sending YOU_WERE_KICKED
    causes the client to close the connection gracefully. The server-side
    disconnect cleanup (finally block in ws_router) handles the rest.
    """
    try:
        parsed = TargetUserMessage.from_dict(msg)
    except (KeyError, TypeError) as e:
        await _send_error(websocket, "invalid_message", f"Malformed kick message: {e}")
        return

    target_user_id = parsed.target_user_id

    # Get actor's role from Redis presence
    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        await room_service.kick_user(room_id, actor_role, target_user_id)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[Mod] kick_user failed room={room_id} target={target_user_id}: {e}")
        await _send_error(websocket, "server_error", "Kick failed. Please try again.")
        return

    # Notify the kicked user — client closes the WS on receipt
    await manager.send_to(room_id, target_user_id, {
        "type":    MsgType.YOU_WERE_KICKED,
        "message": "You have been removed from this room by the host.",
    })

    # Broadcast to room so all clients remove them from presence UI
    await manager.broadcast(room_id, {
        "type":    MsgType.PARTICIPANT_KICKED,
        "user_id": target_user_id,
    }, exclude_user_id=target_user_id)

    logger.info(f"[Mod] kicked user={target_user_id} from room={room_id} by actor={actor_id}")


async def handle_mute(
    websocket: WebSocket,
    msg:       dict,
    room_id:   str,
    actor_id:  str,
) -> None:
    """Mute a participant — they can still read and move cursor, but ops are rejected."""
    try:
        parsed = TargetUserMessage.from_dict(msg)
    except (KeyError, TypeError) as e:
        await _send_error(websocket, "invalid_message", f"Malformed mute message: {e}")
        return

    target_user_id = parsed.target_user_id

    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        await room_service.mute_user(room_id, actor_role, target_user_id)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[Mod] mute_user failed room={room_id} target={target_user_id}: {e}")
        await _send_error(websocket, "server_error", "Mute failed. Please try again.")
        return

    # Tell the muted user directly so client can show them a notice
    await manager.send_to(room_id, target_user_id, {
        "type":    MsgType.YOU_WERE_MUTED,
        "message": "You have been muted by the host.",
    })

    # Broadcast to room so all clients update the muted indicator
    await manager.broadcast(room_id, {
        "type":    MsgType.PARTICIPANT_MUTED,
        "user_id": target_user_id,
    })

    logger.info(f"[Mod] muted user={target_user_id} in room={room_id} by actor={actor_id}")


async def handle_unmute(
    websocket: WebSocket,
    msg:       dict,
    room_id:   str,
    actor_id:  str,
) -> None:
    """Restore a muted participant's ability to send ops."""
    try:
        parsed = TargetUserMessage.from_dict(msg)
    except (KeyError, TypeError) as e:
        await _send_error(websocket, "invalid_message", f"Malformed unmute message: {e}")
        return

    target_user_id = parsed.target_user_id

    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        await room_service.unmute_user(room_id, actor_role, target_user_id)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[Mod] unmute_user failed room={room_id} target={target_user_id}: {e}")
        await _send_error(websocket, "server_error", "Unmute failed. Please try again.")
        return

    await manager.send_to(room_id, target_user_id, {
        "type":    MsgType.YOU_WERE_UNMUTED,
        "message": "You have been unmuted.",
    })

    await manager.broadcast(room_id, {
        "type":    MsgType.PARTICIPANT_UNMUTED,
        "user_id": target_user_id,
    })

    logger.info(f"[Mod] unmuted user={target_user_id} in room={room_id} by actor={actor_id}")


async def handle_promote_cohost(
    websocket: WebSocket,
    msg:       dict,
    room_id:   str,
    actor_id:  str,
) -> None:
    """Promote a participant to cohost. Host-only action."""
    try:
        parsed = TargetUserMessage.from_dict(msg)
    except (KeyError, TypeError) as e:
        await _send_error(websocket, "invalid_message", f"Malformed promote message: {e}")
        return

    target_user_id = parsed.target_user_id

    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        await room_service.promote_cohost(room_id, actor_role, target_user_id)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[Mod] promote_cohost failed room={room_id} target={target_user_id}: {e}")
        await _send_error(websocket, "server_error", "Promote failed. Please try again.")
        return

    # Broadcast to whole room — all clients update role badges in presence UI
    await manager.broadcast(room_id, {
        "type":    MsgType.COHOST_PROMOTED,
        "user_id": target_user_id,
    })

    logger.info(f"[Mod] promoted user={target_user_id} to cohost in room={room_id}")


async def handle_demote_cohost(
    websocket: WebSocket,
    msg:       dict,
    room_id:   str,
    actor_id:  str,
) -> None:
    """Demote the cohost back to participant. Host-only action."""
    try:
        parsed = TargetUserMessage.from_dict(msg)
    except (KeyError, TypeError) as e:
        await _send_error(websocket, "invalid_message", f"Malformed demote message: {e}")
        return

    target_user_id = parsed.target_user_id

    actor_role = await room_state.get_user_role(room_id, actor_id)
    if not actor_role:
        await _send_error(websocket, "server_error", "Could not verify your role.")
        return

    try:
        await room_service.demote_cohost(room_id, actor_role, target_user_id)
    except PermissionError as e:
        await _send_error(websocket, "forbidden", str(e))
        return
    except Exception as e:
        logger.error(f"[Mod] demote_cohost failed room={room_id} target={target_user_id}: {e}")
        await _send_error(websocket, "server_error", "Demote failed. Please try again.")
        return

    await manager.broadcast(room_id, {
        "type":    MsgType.COHOST_DEMOTED,
        "user_id": target_user_id,
    })

    logger.info(f"[Mod] demoted user={target_user_id} from cohost in room={room_id}")


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