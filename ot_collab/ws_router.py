"""
ot_collab/ws_router.py
----------------------
FastAPI router — HTTP endpoints for room management + WebSocket endpoint.

This file is a dispatcher only. It contains:
  - HTTP endpoints for room management (create, get, close)
  - WebSocket endpoint: auth → room load → join gate → relay loop → cleanup
  - No business logic — all delegated to handlers/ and room_service

HTTP endpoints:
  POST /collab/rooms                    create room
  GET  /collab/rooms/{room_id}          room info
  POST /collab/rooms/{room_id}/close    host closes room

WebSocket endpoint:
  WS /collab/ws/{room_id}?session_id={sid}

Auth: session_id query param → Redis lookup → user_id string.
Cookies are unreliable for WebSocket upgrades in browsers.
Same Redis key pattern as auth_middleware.py: session:{session_id} → user_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import db.connection as db_conn
from db.users import get_user_by_id
from core.redis_client import async_redis

from .models import (
    Op, OpType, NoOp,
    MsgType,
    ClientOpMessage, CursorMessage,
    SNAPSHOT_EVERY_N_OPS, JOIN_TIMEOUT_SECONDS,
    assign_color,
)
from . import ot_engine
from . import room_state, room_service
from .db import rooms as db_rooms
from .db import operations as db_ops
from .connection_manager import manager
from .handlers import (
    handle_op, handle_cursor,
    run_password_gate, run_join_flow, handle_approval,
    handle_kick, handle_mute, handle_unmute,
    handle_promote_cohost, handle_demote_cohost,
    handle_lock_room, handle_unlock_room,
    handle_set_password, handle_close_room,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collab", tags=["collaboration"])


# ── HTTP: Create room ─────────────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    title:    str
    password: Optional[str] = None   # optional room password at creation time


@router.post("/rooms")
async def create_room(body: CreateRoomRequest, request: Request):
    """
    Create a new collaboration room.
    Requires login — host must be authenticated.
    If password is provided it is hashed and stored immediately.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required to create a room")

    if not body.title or not body.title.strip():
        raise HTTPException(400, "Room title is required")

    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.create_room(conn, user_id, body.title.strip())
        room_id = str(room["room_id"])

        if body.password:
            from .password_utils import hash_password
            hashed = hash_password(body.password)
            await db_rooms.set_room_password(conn, room_id, hashed)

    # Seed Redis with empty document at revision 0
    await room_state.init_room_in_redis(
        room_id=room_id,
        content="",
        revision=0,
        host_id=user_id,
    )

    return {
        "room_id":      room_id,
        "title":        room["title"],
        "host_id":      str(room["host_id"]),
        "has_password": bool(body.password),
    }


# ── HTTP: Get room info ───────────────────────────────────────────────────────

@router.get("/rooms/{room_id}")
async def get_room_info(room_id: str, request: Request):
    """
    Return room metadata and current participant count.
    Public — anyone can check if a room exists before joining.
    """
    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.get_room(conn, room_id)
        if not room:
            raise HTTPException(404, "Room not found")
        participants = await db_rooms.get_participants(conn, room_id)

    connected_count = manager.get_connection_count(room_id)

    return {
        "room_id":           str(room["room_id"]),
        "title":             room["title"],
        "host_id":           str(room["host_id"]),
        "is_active":         room["is_active"],
        "is_locked":         room["is_locked"],
        "has_password":      bool(room["password_hash"]),
        "participant_count": len(participants),
        "connected_count":   connected_count,
        "created_at":        room["created_at"].isoformat(),
    }


# ── HTTP: Close room ──────────────────────────────────────────────────────────

@router.post("/rooms/{room_id}/close")
async def close_room(room_id: str, request: Request):
    """
    Host closes the room via HTTP (e.g. from a dashboard page outside the WS session).
    For in-session close the client sends CLOSE_ROOM over WebSocket instead.
    Broadcasts room_closed to all connected participants. Saves final snapshot.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.get_room(conn, room_id)
        if not room:
            raise HTTPException(404, "Room not found")
        if str(room["host_id"]) != user_id:
            raise HTTPException(403, "Only the host can close the room")

    try:
        # Permission check bypassed — already verified host above via PG
        await room_service.close_room(room_id, "host")
    except Exception as e:
        logger.error(f"[HTTP] close_room failed room={room_id}: {e}")

    # Broadcast closure to all connected clients
    await manager.broadcast(room_id, {"type": MsgType.ROOM_CLOSED})

    # Expire Redis keys
    await room_state.expire_room(room_id)

    return {"ok": True}


# ── WebSocket helpers ─────────────────────────────────────────────────────────

async def _auth_websocket(session_id: Optional[str]) -> Optional[str]:
    """
    Resolve session_id → user_id via Redis.
    Same key pattern as auth_middleware.py: session:{session_id} → user_id.
    Returns user_id string or None if invalid/expired.
    """
    if not session_id:
        return None
    return await async_redis.get(f"session:{session_id}")


async def _get_username(user_id: str) -> str:
    """Fetch username from PostgreSQL. Falls back to truncated user_id."""
    try:
        async with db_conn.pool.acquire() as conn:
            user = await get_user_by_id(conn, uuid.UUID(user_id))
            if user:
                return user["username"]
    except Exception:
        pass
    return user_id[:8]


async def _ensure_room_in_redis(room_id: str, conn) -> tuple[str, int]:
    """
    Ensure room is live in Redis. If cold (server restart), recover from PG.
    Returns (content, revision).

    recover_room_state() returns a full state dict including metadata
    (is_locked, cohost_id, password_version) so cold-start recovery
    re-seeds Redis completely — not just the document content.
    """
    if await room_state.room_exists_in_redis(room_id):
        return await room_state.get_room_doc(room_id)

    # Cold start — recover from PostgreSQL
    logger.info(f"[WS] Room {room_id} cold in Redis, recovering from PG")
    state = await db_ops.recover_room_state(conn, room_id)

    await room_state.init_room_in_redis(
        room_id=room_id,
        content=state["content"],
        revision=state["revision"],
        host_id=state["host_id"],
        cohost_id=state["cohost_id"],
        is_locked=state["is_locked"],
        password_version=state["password_version"],
    )

    return state["content"], state["revision"]


async def _ws_error(
    websocket: WebSocket,
    code:      str,
    message:   str,
    close:     int = 4000,
) -> None:
    """Send an error message and close the WebSocket."""
    try:
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    code,
            "message": message,
        }))
        await websocket.close(code=close)
    except Exception:
        pass


async def _room_is_active(room_id: str) -> bool:
    """
    Quick PG check — returns False if room was already closed via
    CLOSE_ROOM message before this finally block runs.
    """
    try:
        async with db_conn.pool.acquire() as conn:
            room = await db_rooms.get_room(conn, room_id)
            return bool(room and room["is_active"])
    except Exception:
        return False


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket:  WebSocket,
    room_id:    str,
    session_id: Optional[str] = Query(None),
):
    """
    Main WebSocket endpoint for a collaboration room.

    Flow:
      1.  Auth via session_id query param
      2.  Load room from PG, validate is_active
      3.  Ensure Redis is warm (cold-start recovery if needed)
      4.  Password gate — if room has password and user has no cached auth
      5.  Lock check — reject new joins if room is locked
      6.  Participant check: reconnect path vs new join path
      7.  New join: run approval flow (host/cohost must approve)
      8.  Seed Redis presence with correct role + mute state from PG
      9.  Register connection, send snapshot, broadcast arrival
     10.  Relay loop: dispatch incoming messages to handlers
     11.  Cleanup on disconnect: presence, broadcast departure, grace or expire
    """
    await websocket.accept()

    # ── 1. Auth ───────────────────────────────────────────────────────────────
    user_id = await _auth_websocket(session_id)
    if not user_id:
        await _ws_error(websocket, "auth_failed",
                        "Invalid or expired session. Please log in again.", close=4001)
        return

    username = await _get_username(user_id)

    # ── 2. Load room ──────────────────────────────────────────────────────────
    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.get_room(conn, room_id)

    if not room:
        await _ws_error(websocket, "room_not_found", "Room does not exist.", close=4004)
        return

    if not room["is_active"]:
        await _ws_error(websocket, "room_closed", "This room has been closed.", close=4010)
        return

    host_id = str(room["host_id"])
    is_host = (user_id == host_id)

    # ── 3. Ensure Redis is warm ───────────────────────────────────────────────
    try:
        async with db_conn.pool.acquire() as conn:
            content, revision = await _ensure_room_in_redis(room_id, conn)
    except Exception as e:
        logger.error(f"[WS] Redis init failed room={room_id}: {e}")
        await _ws_error(websocket, "server_error",
                        "Failed to load room state. Please try again.", close=4500)
        return

    # ── 4. Password gate ──────────────────────────────────────────────────────
    # Host is never asked for the room password — they own the room.
    password_hash    = room.get("password_hash")
    password_version = int(room.get("password_version", 0))

    if password_hash and not is_host:
        authorized = await run_password_gate(
            websocket, room_id, user_id, password_hash, password_version
        )
        if not authorized:
            return   # run_password_gate already sent rejection and closed socket

    # ── 5. Lock check ─────────────────────────────────────────────────────────
    # Resolve cohost here — needed for lock bypass and join flow notification.
    cohost_id = await room_state.get_room_cohost(room_id)
    is_cohost = (user_id == cohost_id) if cohost_id else False

    if not is_host and not is_cohost:
        if await room_state.is_room_locked(room_id):
            # Existing approved participants can still reconnect when locked.
            # Only block new users who haven't been approved yet.
            async with db_conn.pool.acquire() as conn:
                already_in = await db_rooms.is_participant(conn, room_id, user_id)
            if not already_in:
                await _ws_error(websocket, "room_locked",
                                "This room is locked and not accepting new participants.",
                                close=4010)
                return

    # ── 6. Participant check: reconnect vs new join ───────────────────────────
    async with db_conn.pool.acquire() as conn:
        participant = await db_rooms.get_participant(conn, room_id, user_id)

    already_participant = participant is not None

    # ── 7. Join flow for new participants ─────────────────────────────────────
    if not already_participant and not is_host:
        approved = await run_join_flow(
            websocket, room_id, user_id, username, host_id, cohost_id
        )
        if not approved:
            return   # rejected or timed out — socket already closed

        # Write approval to PG
        async with db_conn.pool.acquire() as conn:
            await db_rooms.add_participant(conn, room_id, user_id, role="participant")

        # Refresh participant row so role/mute seeding below has real data
        async with db_conn.pool.acquire() as conn:
            participant = await db_rooms.get_participant(conn, room_id, user_id)

    # ── 8. Seed Redis presence with correct role + mute state from PG ─────────
    # Critical correctness fix: role and is_muted always come from PG on join.
    # Prevents the cold-start divergence bug where reconnecting users would
    # get default presence state instead of their actual persisted state.
    if is_host:
        role     = "host"
        is_muted = False
    elif participant:
        role     = participant.get("role", "participant")
        is_muted = bool(participant.get("is_muted", False))
    else:
        role     = "participant"
        is_muted = False

    # ── 9. Register connection + send snapshot ────────────────────────────────
    existing_colors = await room_state.get_existing_colors(room_id)
    color           = assign_color(existing_colors)

    await room_state.add_user_to_room(
        room_id, user_id, username, color, role=role, is_muted=is_muted
    )
    manager.connect(room_id, user_id, websocket)

    # Re-read doc — may have changed while waiting for approval
    try:
        content, revision = await room_state.get_room_doc(room_id)
    except KeyError:
        content, revision = "", 0

    # Build presence list for client initialization
    room_users = await room_state.get_room_users(room_id)
    users_list = [
        {
            "user_id":  uid,
            "username": d["username"],
            "color":    d["color"],
            "role":     d["role"],
            "is_muted": d["is_muted"],
        }
        for uid, d in room_users.items()
    ]

    # If host is reconnecting during an active grace period, cancel it
    if is_host:
        grace = await room_state.get_host_grace(room_id)
        if grace is not None:
            await room_service.handle_host_rejoin(room_id)
            await manager.broadcast(room_id, {
                "type": MsgType.HOST_REJOINED,
            }, exclude_user_id=user_id)
            logger.info(f"[WS] host rejoined room={room_id}, grace period cancelled")

    await websocket.send_text(json.dumps({
        "type":      MsgType.JOIN_APPROVED,
        "content":   content,
        "revision":  revision,
        "users":     users_list,
        "your_role": role,
    }))

    # Announce arrival to others
    await manager.broadcast(room_id, {
        "type":     MsgType.PARTICIPANT_JOINED,
        "user_id":  user_id,
        "username": username,
        "color":    color,
        "role":     role,
    }, exclude_user_id=user_id)

    logger.info(f"[WS] user={username} role={role} joined room={room_id} rev={revision}")

    # ── 10. Relay loop ────────────────────────────────────────────────────────
    # Manual background task executor for WebSockets (standard BackgroundTasks 
    # only run after the function returns, which is too late for a persistent WS).
    class ImmediateBackgroundTasks:
        def add_task(self, func, *args, **kwargs):
            asyncio.create_task(func(*args, **kwargs))

    background = ImmediateBackgroundTasks()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type":    MsgType.ERROR,
                    "code":    "invalid_json",
                    "message": "Message must be valid JSON.",
                }))
                continue

            msg_type = msg.get("type")

            # ── op ────────────────────────────────────────────────────────────
            if msg_type == MsgType.OP:
                await handle_op(websocket, msg, room_id, user_id, background)

            # ── cursor ────────────────────────────────────────────────────────
            elif msg_type == MsgType.CURSOR:
                await handle_cursor(msg, room_id, user_id)

            # ── approve / reject join ─────────────────────────────────────────
            elif msg_type == MsgType.APPROVE_USER or msg_type == MsgType.REJECT_USER:
                actor_role = await room_state.get_user_role(room_id, user_id)
                if actor_role in ["host", "cohost"]:
                    await handle_approval(msg, room_id, approved=(msg_type == MsgType.APPROVE_USER))
                else:
                    await websocket.send_text(json.dumps({
                        "type":    MsgType.ERROR,
                        "code":    "forbidden",
                        "message": "Only host or cohost can approve participants.",
                    }))

            # ── moderation ────────────────────────────────────────────────────
            elif msg_type == MsgType.KICK_USER:
                await handle_kick(websocket, msg, room_id, user_id)

            elif msg_type == MsgType.MUTE_USER:
                await handle_mute(websocket, msg, room_id, user_id)

            elif msg_type == MsgType.UNMUTE_USER:
                await handle_unmute(websocket, msg, room_id, user_id)

            elif msg_type == MsgType.PROMOTE_COHOST:
                await handle_promote_cohost(websocket, msg, room_id, user_id)

            elif msg_type == MsgType.DEMOTE_COHOST:
                await handle_demote_cohost(websocket, msg, room_id, user_id)

            # ── room control ──────────────────────────────────────────────────
            elif msg_type == MsgType.LOCK_ROOM:
                await handle_lock_room(websocket, room_id, user_id)

            elif msg_type == MsgType.UNLOCK_ROOM:
                await handle_unlock_room(websocket, room_id, user_id)

            elif msg_type == MsgType.SET_PASSWORD:
                await handle_set_password(websocket, msg, room_id, user_id)

            elif msg_type == MsgType.CLOSE_ROOM:
                await handle_close_room(websocket, room_id, user_id, background)
                break   # relay loop exits — finally block handles cleanup

            else:
                logger.debug(f"[WS] unknown msg type={msg_type} user={user_id}")

    except WebSocketDisconnect:
        logger.info(f"[WS] disconnected user={username} room={room_id}")

    except Exception as e:
        logger.error(f"[WS] relay loop error user={user_id} room={room_id}: {e}")

    finally:
        # ── 11. Cleanup on disconnect ─────────────────────────────────────────
        manager.disconnect(room_id, user_id)
        await room_state.remove_user_from_room(room_id, user_id)

        if is_host:
            # Check if room was already closed cleanly via CLOSE_ROOM message.
            # If so, handle_close_room already broadcast ROOM_CLOSED and expired
            # Redis — don't start a grace period on top of a clean close.
            room_still_active = await _room_is_active(room_id)
            grace_active      = await room_state.get_host_grace(room_id)

            if room_still_active and grace_active is None:
                # Unclean disconnect — save snapshot, start grace period
                grace_until = await room_service.handle_host_disconnect(room_id)
                await manager.broadcast(room_id, {
                    "type":        MsgType.HOST_DISCONNECTED,
                    "grace_until": grace_until,
                })
                logger.info(
                    f"[WS] host disconnected room={room_id}, "
                    f"grace started until={grace_until}"
                )
        else:
            await manager.broadcast(room_id, {
                "type":    MsgType.PARTICIPANT_LEFT,
                "user_id": user_id,
            })

        # If no one left, decide whether to expire Redis or preserve it.
        if manager.get_connection_count(room_id) == 0:
            grace_active = await room_state.get_host_grace(room_id)
            if grace_active is None:
                # No grace period running — safe to take final snapshot and expire
                try:
                    content, revision = await room_state.get_room_doc(room_id)
                    async with db_conn.pool.acquire() as conn:
                        await db_ops.save_snapshot(conn, room_id, content, revision)
                        await db_rooms.update_room_revision(conn, room_id, revision)
                except Exception as e:
                    logger.warning(f"[WS] final snapshot failed room={room_id}: {e}")
                await room_state.expire_room(room_id)
            else:
                # Grace period active — host may rejoin.
                # Keep Redis alive. Sweeper closes the room if host never returns.
                logger.info(
                    f"[WS] last participant left room={room_id} "
                    f"but grace period active — Redis preserved for host rejoin"
                )