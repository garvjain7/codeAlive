"""
ot_collab/ws_router.py
----------------------
FastAPI router — HTTP endpoints for room management + WebSocket endpoint.

This file contains NO logic. It orchestrates calls to:
  ot_engine      → transform math
  room_state     → Redis reads/writes
  db/rooms       → PostgreSQL room/participant queries
  db/operations  → PostgreSQL op log/snapshot queries
  connection_manager → WebSocket registry + broadcast

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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import db.connection as db_conn
from db.users import get_user_by_id
from redis_client import async_redis

from .models import (
    Op, OpType, NoOp,
    MsgType,
    ClientOpMessage, CursorMessage, ApproveRejectMessage,
    SNAPSHOT_EVERY_N_OPS, JOIN_TIMEOUT_SECONDS,
    assign_color,
)
from . import ot_engine
from . import room_state
from .db import rooms as db_rooms
from .db import operations as db_ops
from .connection_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collab", tags=["collaboration"])


# ── HTTP: Create room ─────────────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    title: str


@router.post("/rooms")
async def create_room(body: CreateRoomRequest, request: Request):
    """
    Create a new collaboration room.
    Requires login — host must be authenticated.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required to create a room")

    if not body.title or not body.title.strip():
        raise HTTPException(400, "Room title is required")

    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.create_room(conn, user_id, body.title.strip())

    # Seed Redis with empty document at revision 0
    await room_state.init_room_in_redis(
        room_id=str(room["room_id"]),
        content="",
        revision=0,
        host_id=user_id,
    )

    return {
        "room_id": str(room["room_id"]),
        "title":   room["title"],
        "host_id": str(room["host_id"]),
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
        "room_id":         str(room["room_id"]),
        "title":           room["title"],
        "host_id":         str(room["host_id"]),
        "is_active":       room["is_active"],
        "participant_count": len(participants),
        "connected_count": connected_count,
        "created_at":      room["created_at"].isoformat(),
    }


# ── HTTP: Close room ──────────────────────────────────────────────────────────

@router.post("/rooms/{room_id}/close")
async def close_room(room_id: str, request: Request):
    """
    Host closes the room. Broadcasts room_closed to all participants.
    Saves final snapshot to PostgreSQL. Expires Redis keys.
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

        # Save final snapshot
        try:
            content, revision = await room_state.get_room_doc(room_id)
            await db_ops.save_snapshot(conn, room_id, content, revision)
            await db_rooms.update_room_revision(conn, room_id, revision)
        except KeyError:
            pass  # Redis already cold — PG is already the source of truth

        await db_rooms.set_room_inactive(conn, room_id)

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
    """
    if await room_state.room_exists_in_redis(room_id):
        return await room_state.get_room_doc(room_id)

    # Cold start — recover from PostgreSQL
    logger.info(f"[WS] Room {room_id} cold in Redis, recovering from PG")
    content, revision = await db_ops.recover_room_state(conn, room_id)

    room = await db_rooms.get_room(conn, room_id)
    host_id = str(room["host_id"]) if room else ""

    await room_state.init_room_in_redis(room_id, content, revision, host_id)
    return content, revision


async def _maybe_save_snapshot(
    room_id:    str,
    content:    str,
    revision:   int,
    background: BackgroundTasks,
) -> None:
    """
    Save a snapshot if we've hit the threshold.
    Runs as a background task — not on the critical path.
    """
    if revision % SNAPSHOT_EVERY_N_OPS == 0:
        async def _save():
            try:
                async with db_conn.pool.acquire() as conn:
                    await db_ops.save_snapshot(conn, room_id, content, revision)
                    await db_rooms.update_room_revision(conn, room_id, revision)
            except Exception as e:
                logger.error(f"[WS] snapshot save failed room={room_id}: {e}")
        background.add_task(_save)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id:   str,
    session_id: Optional[str] = None,
):
    """
    Main WebSocket endpoint for a collaboration room.

    Flow:
      1. Auth via session_id query param
      2. Load room from PG, ensure Redis is warm
      3. Check if already a participant (reconnect) or new (join flow)
      4. For new users: notify host, wait for approval with timeout
      5. On approval: register connection, send snapshot, begin relay loop
      6. Relay loop: handle op | cursor | approve | reject | close
      7. On disconnect: cleanup, broadcast departure
    """
    await websocket.accept()

    # ── 1. Auth ───────────────────────────────────────────────────────────────
    user_id = await _auth_websocket(session_id)
    if not user_id:
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "auth_failed",
            "message": "Invalid or expired session. Please log in again.",
        }))
        await websocket.close(code=4001)
        return

    username = await _get_username(user_id)

    # ── 2. Load room ──────────────────────────────────────────────────────────
    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.get_room(conn, room_id)

    if not room:
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "room_not_found",
            "message": "Room does not exist.",
        }))
        await websocket.close(code=4004)
        return

    if not room["is_active"]:
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "room_closed",
            "message": "This room has been closed.",
        }))
        await websocket.close(code=4010)
        return

    host_id = str(room["host_id"])

    # ── 3. Ensure Redis is warm ───────────────────────────────────────────────
    try:
        async with db_conn.pool.acquire() as conn:
            content, revision = await _ensure_room_in_redis(room_id, conn)
    except Exception as e:
        logger.error(f"[WS] Redis init failed room={room_id}: {e}")
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "server_error",
            "message": "Failed to load room state. Please try again.",
        }))
        await websocket.close(code=4500)
        return

    # ── 4. Participant check: reconnect vs new join ───────────────────────────
    async with db_conn.pool.acquire() as conn:
        already_participant = await db_rooms.is_participant(conn, room_id, user_id)

    is_host = (user_id == host_id)

    if not already_participant and not is_host:
        # New user — need host approval
        approved = await _handle_join_flow(
            websocket, room_id, user_id, username, host_id
        )
        if not approved:
            return  # rejected or timed out — socket already closed

        # Write approval to PG
        async with db_conn.pool.acquire() as conn:
            await db_rooms.add_participant(conn, room_id, user_id)

    elif is_host:
        # Host is always a participant on first connect
        async with db_conn.pool.acquire() as conn:
            await db_rooms.add_participant(conn, room_id, user_id)

    # ── 5. Register connection + send snapshot ────────────────────────────────
    # Assign color
    existing_colors = await room_state.get_existing_colors(room_id)
    color = assign_color(existing_colors)

    await room_state.add_user_to_room(room_id, user_id, username, color)
    manager.connect(room_id, user_id, websocket)

    # Re-read doc (may have changed while waiting for approval)
    try:
        content, revision = await room_state.get_room_doc(room_id)
    except KeyError:
        content, revision = "", 0

    # Current users for presence initialization
    room_users = await room_state.get_room_users(room_id)
    users_list = [
        {"user_id": uid, "username": d["username"], "color": d["color"]}
        for uid, d in room_users.items()
    ]

    await websocket.send_text(json.dumps({
        "type":     MsgType.JOIN_APPROVED,
        "content":  content,
        "revision": revision,
        "users":    users_list,
    }))

    # Announce arrival to others
    await manager.broadcast(room_id, {
        "type":     MsgType.PARTICIPANT_JOINED,
        "user_id":  user_id,
        "username": username,
        "color":    color,
    }, exclude_user_id=user_id)

    logger.info(f"[WS] user={username} joined room={room_id} rev={revision}")

    # ── 6. Relay loop ─────────────────────────────────────────────────────────
    background = BackgroundTasks()

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
                await _handle_op(
                    websocket, msg, room_id, user_id, background
                )

            # ── cursor ────────────────────────────────────────────────────────
            elif msg_type == MsgType.CURSOR:
                await _handle_cursor(msg, room_id, user_id)

            # ── approve_user ──────────────────────────────────────────────────
            elif msg_type == MsgType.APPROVE_USER:
                if user_id != host_id:
                    await websocket.send_text(json.dumps({
                        "type":    MsgType.ERROR,
                        "code":    "not_host",
                        "message": "Only the host can approve users.",
                    }))
                    continue
                await _handle_approval(msg, room_id, approved=True)

            # ── reject_user ───────────────────────────────────────────────────
            elif msg_type == MsgType.REJECT_USER:
                if user_id != host_id:
                    await websocket.send_text(json.dumps({
                        "type":    MsgType.ERROR,
                        "code":    "not_host",
                        "message": "Only the host can reject users.",
                    }))
                    continue
                await _handle_approval(msg, room_id, approved=False)

            # ── close_room ────────────────────────────────────────────────────
            elif msg_type == MsgType.CLOSE_ROOM:
                if user_id != host_id:
                    continue
                await _handle_close_room(room_id, user_id, background)
                break  # exit relay loop after closing

            else:
                logger.debug(f"[WS] unknown msg type={msg_type} user={user_id}")

    except WebSocketDisconnect:
        logger.info(f"[WS] disconnected user={username} room={room_id}")

    except Exception as e:
        logger.error(f"[WS] relay loop error user={user_id} room={room_id}: {e}")

    finally:
        # ── 7. Cleanup on disconnect ──────────────────────────────────────────
        manager.disconnect(room_id, user_id)
        await room_state.remove_user_from_room(room_id, user_id)

        if user_id == host_id:
            await manager.broadcast(room_id, {"type": MsgType.HOST_DISCONNECTED})
        else:
            await manager.broadcast(room_id, {
                "type":    MsgType.PARTICIPANT_LEFT,
                "user_id": user_id,
            })

        # If no one left, expire Redis keys
        if manager.get_connection_count(room_id) == 0:
            try:
                content, revision = await room_state.get_room_doc(room_id)
                async with db_conn.pool.acquire() as conn:
                    await db_ops.save_snapshot(conn, room_id, content, revision)
                    await db_rooms.update_room_revision(conn, room_id, revision)
            except Exception as e:
                logger.warning(f"[WS] final snapshot failed room={room_id}: {e}")
            await room_state.expire_room(room_id)


# ── Join flow ─────────────────────────────────────────────────────────────────

async def _handle_join_flow(
    websocket: WebSocket,
    room_id:   str,
    user_id:   str,
    username:  str,
    host_id:   str,
) -> bool:
    """
    Handle the join approval flow for a new participant.

    Creates a join request in PG, notifies host, waits for host response
    with a JOIN_TIMEOUT_SECONDS timeout.

    Uses an asyncio.Event as the signaling mechanism:
      - Host sends approve_user / reject_user
      - _handle_approval() sets the event
      - This function awaits the event with timeout

    Returns True if approved, False if rejected or timed out.
    """
    # Create join request in PG
    async with db_conn.pool.acquire() as conn:
        request = await db_rooms.create_join_request(conn, room_id, user_id)
    request_id = str(request["id"])

    # Store the event in a module-level dict so _handle_approval can signal it
    event: asyncio.Event = asyncio.Event()
    result_container: dict = {"approved": False}
    _pending_join_events[request_id] = (event, result_container)

    # Notify host
    host_notified = await manager.send_to_host(room_id, host_id, {
        "type":       MsgType.JOIN_REQUEST,
        "user_id":    user_id,
        "username":   username,
        "request_id": request_id,
    })

    if not host_notified:
        # Host is not connected — auto-reject
        _pending_join_events.pop(request_id, None)
        await websocket.send_text(json.dumps({
            "type":    MsgType.JOIN_REJECTED,
            "message": "The room host is not currently connected.",
        }))
        await websocket.close(code=4003)
        return False

    # Wait for host response with timeout
    try:
        await asyncio.wait_for(event.wait(), timeout=JOIN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        _pending_join_events.pop(request_id, None)
        await websocket.send_text(json.dumps({
            "type":    MsgType.JOIN_REJECTED,
            "message": "Join request timed out. The host did not respond.",
        }))
        await websocket.close(code=4008)
        return False

    _pending_join_events.pop(request_id, None)
    approved = result_container["approved"]

    if not approved:
        await websocket.send_text(json.dumps({
            "type":    MsgType.JOIN_REJECTED,
            "message": "The host declined your request to join.",
        }))
        await websocket.close(code=4003)
        return False

    return True


# Module-level dict: request_id → (asyncio.Event, result_container)
# Holds pending join approvals waiting for host response.
_pending_join_events: dict[str, tuple[asyncio.Event, dict]] = {}


async def _handle_approval(msg: dict, room_id: str, approved: bool) -> None:
    """
    Host sent approve_user or reject_user.
    Signals the waiting _handle_join_flow coroutine via asyncio.Event.
    Also persists the decision to PostgreSQL.
    """
    target_user_id = msg.get("target_user_id")
    request_id     = msg.get("request_id")

    if not target_user_id or not request_id:
        return

    # Persist decision to PG
    status = "approved" if approved else "rejected"
    try:
        async with db_conn.pool.acquire() as conn:
            await db_rooms.resolve_join_request(conn, request_id, status)
    except Exception as e:
        logger.error(f"[WS] resolve_join_request failed: {e}")

    # Signal the waiting coroutine
    entry = _pending_join_events.get(request_id)
    if entry:
        event, result_container = entry
        result_container["approved"] = approved
        event.set()


# ── Op handler ────────────────────────────────────────────────────────────────

async def _handle_op(
    websocket:  WebSocket,
    msg:        dict,
    room_id:    str,
    user_id:    str,
    background: BackgroundTasks,
) -> None:
    """
    The critical path — handle an incoming operation from a client.

    Steps:
      1. Parse and validate the ClientOpMessage
      2. Fetch history since client_revision from Redis
      3. Transform op against history (catchup)
      4. If transform yields NoOp — ack with current rev, nothing to apply
      5. Atomically apply op to Redis (WATCH/MULTI/EXEC)
      6. Ack sender with new revision + transformed op
      7. Broadcast to all other participants
      8. Background: persist op to PostgreSQL
      9. Background: maybe save snapshot

    Database analogy for steps 2-5:
      Step 2 = read the missed committed transactions
      Step 3 = rebase our pending transaction on top of them
      Step 5 = commit (with optimistic lock — retry on conflict)
    """
    # ── 1. Parse ──────────────────────────────────────────────────────────────
    try:
        client_msg = ClientOpMessage.from_dict(msg)
    except (KeyError, ValueError, TypeError) as e:
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "invalid_op",
            "message": f"Malformed operation: {e}",
        }))
        return

    op              = client_msg.op
    op_id           = client_msg.op_id
    client_revision = client_msg.client_revision

    # ── 2. Fetch history since client_revision ────────────────────────────────
    try:
        history_ops = await room_state.get_history_since(room_id, client_revision)
    except Exception as e:
        logger.error(f"[WS] get_history_since failed room={room_id}: {e}")
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "server_error",
            "message": "Failed to fetch operation history.",
        }))
        return

    # ── 3. Transform op against concurrent history ops ────────────────────────
    # This is the OT catchup.
    # Each op in history was applied after the client's last known revision.
    # We transform our op against each of them in order.
    #
    # Database analogy:
    #   history_ops = committed transactions the client missed
    #   transform_against_many = replaying those commits and rebasing
    if history_ops:
        transformed = ot_engine.transform_against_many(op, history_ops)
    else:
        transformed = op

    # ── 4. NoOp check ─────────────────────────────────────────────────────────
    # If transform yielded NoOp (op fully cancelled by concurrent deletes),
    # ack the client with current revision — nothing to apply.
    if isinstance(transformed, NoOp):
        try:
            _, current_rev = await room_state.get_room_doc(room_id)
        except KeyError:
            current_rev = client_revision
        await websocket.send_text(json.dumps({
            "type":     MsgType.OP_ACK,
            "op_id":    op_id,
            "revision": current_rev,
            "op":       op.to_dict(),  # echo original — client clears inflight
        }))
        return

    transformed_op: Op = transformed  # type: ignore

    # ── 5. Atomic apply to Redis ──────────────────────────────────────────────
    try:
        _, new_revision = await room_state.apply_op_to_room(room_id, transformed_op)
    except ValueError as e:
        # op bounds invalid — client state diverged, tell them to reconnect
        logger.error(f"[WS] apply failed room={room_id} user={user_id}: {e}")
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "apply_failed",
            "message": "Operation could not be applied. Please reconnect.",
        }))
        return
    except RuntimeError as e:
        # All retries exhausted — extreme contention
        logger.error(f"[WS] apply retries exhausted room={room_id}: {e}")
        await websocket.send_text(json.dumps({
            "type":    MsgType.ERROR,
            "code":    "server_error",
            "message": "Server is under heavy load. Please retry.",
        }))
        return

    # ── 6. Ack sender ─────────────────────────────────────────────────────────
    # Send the TRANSFORMED op back with new revision.
    # Client uses this to:
    #   a) Confirm inflight_op was applied
    #   b) Know the new confirmed_doc.revision
    #   c) Get the server-side adjusted position (transformed op)
    await websocket.send_text(json.dumps({
        "type":     MsgType.OP_ACK,
        "op_id":    op_id,
        "revision": new_revision,
        "op":       transformed_op.to_dict(),
    }))

    # ── 7. Broadcast to others ────────────────────────────────────────────────
    await manager.broadcast(room_id, {
        "type":     MsgType.OP_BROADCAST,
        "op":       transformed_op.to_dict(),
        "revision": new_revision,
        "user_id":  user_id,
    }, exclude_user_id=user_id)

    # ── 8. Persist op to PostgreSQL (background) ──────────────────────────────
    # Not on critical path. If this fails, op is still in Redis history.
    # The next snapshot will capture the document state anyway.
    async def _persist():
        try:
            async with db_conn.pool.acquire() as conn:
                await db_ops.persist_op(
                    conn, room_id, user_id, op_id, new_revision, transformed_op
                )
        except Exception as e:
            logger.error(f"[WS] persist_op failed room={room_id} rev={new_revision}: {e}")

    background.add_task(_persist)

    # ── 9. Maybe snapshot ─────────────────────────────────────────────────────
    if new_revision % SNAPSHOT_EVERY_N_OPS == 0:
        try:
            content, _ = await room_state.get_room_doc(room_id)
            await _maybe_save_snapshot(room_id, content, new_revision, background)
        except Exception:
            pass


# ── Cursor handler ────────────────────────────────────────────────────────────

async def _handle_cursor(msg: dict, room_id: str, user_id: str) -> None:
    """
    Update cursor position in Redis and broadcast to room.
    Lossy — if this fails silently, the next cursor message corrects it.
    No database write. No ack.
    """
    try:
        line = int(msg.get("line", 1))
        col  = int(msg.get("col",  0))
    except (TypeError, ValueError):
        return

    await room_state.update_user_cursor(room_id, user_id, line, col)
    await manager.broadcast(room_id, {
        "type":    MsgType.CURSOR_BROADCAST,
        "user_id": user_id,
        "line":    line,
        "col":     col,
    }, exclude_user_id=user_id)


# ── Close room handler ────────────────────────────────────────────────────────

async def _handle_close_room(
    room_id:    str,
    host_id:    str,
    background: BackgroundTasks,
) -> None:
    """
    Host closes the room from within the WebSocket relay loop.
    Saves final snapshot, marks room inactive, broadcasts closure.
    """
    try:
        content, revision = await room_state.get_room_doc(room_id)

        async def _finalize():
            try:
                async with db_conn.pool.acquire() as conn:
                    await db_ops.save_snapshot(conn, room_id, content, revision)
                    await db_rooms.update_room_revision(conn, room_id, revision)
                    await db_rooms.set_room_inactive(conn, room_id)
            except Exception as e:
                logger.error(f"[WS] close_room finalize failed room={room_id}: {e}")

        background.add_task(_finalize)
    except KeyError:
        pass

    await manager.broadcast(room_id, {"type": MsgType.ROOM_CLOSED})
    await room_state.expire_room(room_id)