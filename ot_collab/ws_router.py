"""
ot_collab/ws_router.py
----------------------
FastAPI router — WebSocket endpoint for real-time collaboration.
Focuses on stateful stream relaying. HTTP metadata is in api/collab_router.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request, BackgroundTasks, Query
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

# NOTE: The prefix /collab is shared with collab_http_router in api/
router = APIRouter(prefix="/collab", tags=["collaboration"])

# ── WebSocket helpers ─────────────────────────────────────────────────────────

async def _auth_websocket(session_id: Optional[str]) -> Optional[str]:
    """Resolve session_id -> user_id via Redis."""
    if not session_id:
        return None
    return await async_redis.get(f"session:{session_id}")

async def _get_username(user_id: str) -> str:
    """Fetch username from PostgreSQL."""
    try:
        async with db_conn.pool.acquire() as conn:
            user = await get_user_by_id(conn, uuid.UUID(user_id))
            if user:
                return user["username"]
    except Exception:
        pass
    return user_id[:8]

async def _ensure_room_in_redis(room_id: str, conn) -> tuple[str, int]:
    """Ensure room is live in Redis. Recover from PG if cold."""
    if await room_state.room_exists_in_redis(room_id):
        return await room_state.get_room_doc(room_id)

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

async def _ws_error(websocket: WebSocket, code: str, message: str, close: int = 4000) -> None:
    """Send error and close socket."""
    try:
        await websocket.send_text(json.dumps({
            "type": MsgType.ERROR,
            "code": code,
            "message": message,
        }))
        await websocket.close(code=close)
    except Exception:
        pass

async def _room_is_active(room_id: str) -> bool:
    try:
        async with db_conn.pool.acquire() as conn:
            room = await db_rooms.get_room(conn, room_id)
            return bool(room and room["is_active"])
    except Exception:
        return False

# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    session_id: Optional[str] = Query(None),
):
    """Main WebSocket relay loop."""
    await websocket.accept()

    # 1. Auth
    user_id = await _auth_websocket(session_id)
    if not user_id:
        await _ws_error(websocket, "auth_failed", "Login required", close=4001)
        return

    username = await _get_username(user_id)

    # 2. Load room
    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.get_room(conn, room_id)

    if not room:
        await _ws_error(websocket, "room_not_found", "Room not found", close=4004)
        return
    if not room["is_active"]:
        await _ws_error(websocket, "room_closed", "Room closed", close=4010)
        return

    host_id = str(room["host_id"])
    is_host = (user_id == host_id)

    # 3. Ensure Redis warm
    try:
        async with db_conn.pool.acquire() as conn:
            content, revision = await _ensure_room_in_redis(room_id, conn)
    except Exception as e:
        logger.error(f"[WS] Redis init failed: {e}")
        await _ws_error(websocket, "server_error", "Failed to load room", close=4500)
        return

    # 4. Gate checks (Password/Join Approval)
    password_hash = room.get("password_hash")
    password_version = int(room.get("password_version", 0))
    if password_hash and not is_host:
        authorized = await run_password_gate(websocket, room_id, user_id, password_hash, password_version)
        if not authorized: return

    cohost_id = await room_state.get_room_cohost(room_id)
    is_cohost = (user_id == cohost_id) if cohost_id else False

    async with db_conn.pool.acquire() as conn:
        participant = await db_rooms.get_participant(conn, room_id, user_id)
    
    if not participant and not is_host:
        approved = await run_join_flow(websocket, room_id, user_id, username, host_id, cohost_id)
        if not approved: return
        async with db_conn.pool.acquire() as conn:
            await db_rooms.add_participant(conn, room_id, user_id, role="participant")
            participant = await db_rooms.get_participant(conn, room_id, user_id)

    # 5. Seed Presence
    role = "host" if is_host else (participant.get("role", "participant") if participant else "participant")
    is_muted = bool(participant.get("is_muted", False)) if participant else False
    
    existing_colors = await room_state.get_existing_colors(room_id)
    color = assign_color(existing_colors)
    await room_state.add_user_to_room(room_id, user_id, username, color, role=role, is_muted=is_muted)
    manager.connect(room_id, user_id, websocket)

    # 6. Send Initial State
    room_users = await room_state.get_room_users(room_id)
    users_list = [{"user_id": uid, "username": d["username"], "color": d["color"], "role": d["role"], "is_muted": d["is_muted"]} for uid, d in room_users.items()]
    
    if is_host:
        await room_service.handle_host_rejoin(room_id)
        await manager.broadcast(room_id, {"type": MsgType.HOST_REJOINED}, exclude_user_id=user_id)

    await websocket.send_text(json.dumps({
        "type": MsgType.JOIN_APPROVED,
        "content": content,
        "revision": revision,
        "users": users_list,
        "your_role": role,
    }))

    await manager.broadcast(room_id, {
        "type": MsgType.PARTICIPANT_JOINED,
        "user_id": user_id,
        "username": username,
        "color": color,
        "role": role,
    }, exclude_user_id=user_id)

    # 7. Relay Loop
    class ImmediateBackgroundTasks:
        def add_task(self, func, *args, **kwargs): asyncio.create_task(func(*args, **kwargs))
    background = ImmediateBackgroundTasks()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == MsgType.OP: await handle_op(websocket, msg, room_id, user_id, background)
            elif mtype == MsgType.CURSOR: await handle_cursor(msg, room_id, user_id)
            elif mtype in [MsgType.APPROVE_USER, MsgType.REJECT_USER]:
                role = await room_state.get_user_role(room_id, user_id)
                if role in ["host", "cohost"]: await handle_approval(msg, room_id, approved=(mtype == MsgType.APPROVE_USER))
            elif mtype == MsgType.KICK_USER: await handle_kick(websocket, msg, room_id, user_id)
            elif mtype == MsgType.MUTE_USER: await handle_mute(websocket, msg, room_id, user_id)
            elif mtype == MsgType.UNMUTE_USER: await handle_unmute(websocket, msg, room_id, user_id)
            elif mtype == MsgType.CLOSE_ROOM:
                await handle_close_room(websocket, room_id, user_id, background)
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(room_id, user_id)
        await room_state.remove_user_from_room(room_id, user_id)
        if is_host:
            if await _room_is_active(room_id):
                grace_until = await room_service.handle_host_disconnect(room_id)
                await manager.broadcast(room_id, {"type": MsgType.HOST_DISCONNECTED, "grace_until": grace_until})
        else:
            await manager.broadcast(room_id, {"type": MsgType.PARTICIPANT_LEFT, "user_id": user_id})
        
        if manager.get_connection_count(room_id) == 0:
            if await room_state.get_host_grace(room_id) is None:
                await room_state.expire_room(room_id)