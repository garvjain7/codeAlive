"""
ot_collab/handlers/joins.py
----------------------------
Handles the full join lifecycle:
  1. Password gate (if room has password)
  2. Join request flow (host/cohost approval)
  3. Approval / rejection signals from host

The _pending_join_events dict uses user_id as key (not request_id) to
prevent the double-request race condition where two rapid requests from
the same user create two events but only one coroutine is waiting.
"""

from __future__ import annotations
import asyncio
import json
import logging

from fastapi import WebSocket

import db.connection as db_conn
from ..models import MsgType, JOIN_TIMEOUT_SECONDS
from .. import room_state
from ..db import rooms as db_rooms
from ..password_utils import verify_password

logger = logging.getLogger(__name__)

# user_id → (asyncio.Event, result_container)
# Keyed by user_id so duplicate join attempts from same user reuse the same slot.
_pending_join_events: dict[str, tuple[asyncio.Event, dict]] = {}


async def run_password_gate(
    websocket:        WebSocket,
    room_id:          str,
    user_id:          str,
    password_hash:    str,
    password_version: int,
) -> bool:
    """
    Gate the join flow behind a password check.

    First checks the Redis auth cache — if the user has a valid cached
    authorization for the current password version, they pass immediately
    without re-entering the password.

    If no valid cache entry, sends PASSWORD_REQUIRED and waits for the
    client to respond with a PASSWORD_SUBMIT message.

    Returns True if authorized, False if rejected or timed out.
    """
    # ── Check auth cache first ─────────────────────────────────────────────────
    cached = await room_state.get_room_auth(room_id, user_id, password_version)
    if cached:
        logger.debug(f"[Join] user={user_id} room={room_id} auth cache hit")
        return True

    # ── Prompt for password ────────────────────────────────────────────────────
    await websocket.send_text(json.dumps({
        "type": MsgType.PASSWORD_REQUIRED,
    }))

    # Wait for PASSWORD_SUBMIT with a timeout
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=60.0,           # 60 seconds to enter password
        )
    except asyncio.TimeoutError:
        await websocket.send_text(json.dumps({
            "type":    MsgType.PASSWORD_REJECTED,
            "message": "Password entry timed out.",
        }))
        await websocket.close(code=4008)
        return False

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({
            "type":    MsgType.PASSWORD_REJECTED,
            "message": "Invalid message format.",
        }))
        await websocket.close(code=4003)
        return False

    if msg.get("type") != MsgType.PASSWORD_SUBMIT:
        await websocket.send_text(json.dumps({
            "type":    MsgType.PASSWORD_REJECTED,
            "message": "Expected password submission.",
        }))
        await websocket.close(code=4003)
        return False

    submitted = msg.get("password", "")
    if not verify_password(submitted, password_hash):
        await websocket.send_text(json.dumps({
            "type":    MsgType.PASSWORD_REJECTED,
            "message": "Incorrect password.",
        }))
        await websocket.close(code=4003)
        return False

    # ── Password correct — cache authorization ─────────────────────────────────
    await room_state.set_room_auth(room_id, user_id, password_version)

    await websocket.send_text(json.dumps({
        "type": MsgType.PASSWORD_ACCEPTED,
    }))

    logger.info(f"[Join] user={user_id} room={room_id} password accepted, auth cached")
    return True


async def run_join_flow(
    websocket:  WebSocket,
    room_id:    str,
    user_id:    str,
    username:   str,
    host_id:    str,
    cohost_id:  str | None,
) -> bool:
    """
    Handle the approval flow for a new participant.

    Creates a join request in PG, notifies host (or cohost if host
    is not connected), waits for approval with timeout.

    Returns True if approved, False if rejected or timed out.
    """
    # Guard: if this user already has a pending event slot, reuse it
    # (handles rapid reconnect before previous request resolved)
    if user_id in _pending_join_events:
        existing_event, existing_result = _pending_join_events[user_id]
        if not existing_event.is_set():
            logger.debug(f"[Join] user={user_id} reusing existing pending event")
            # Let the previous wait resolve — do not create a new request
            try:
                await asyncio.wait_for(
                    existing_event.wait(), timeout=JOIN_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                _pending_join_events.pop(user_id, None)
                await _send_rejected(websocket, "Join request timed out.")
                return False
            _pending_join_events.pop(user_id, None)
            return existing_result.get("approved", False)

    # ── Create join request in PG ──────────────────────────────────────────────
    async with db_conn.pool.acquire() as conn:
        request = await db_rooms.create_join_request(conn, room_id, user_id)
    request_id = str(request["id"])

    # ── Register pending event keyed by user_id ───────────────────────────────
    event:            asyncio.Event = asyncio.Event()
    result_container: dict          = {"approved": False, "request_id": request_id}
    _pending_join_events[user_id]   = (event, result_container)

    # ── Notify host or cohost ──────────────────────────────────────────────────
    from ..connection_manager import manager

    join_notification = {
        "type":       MsgType.JOIN_REQUEST,
        "user_id":    user_id,
        "username":   username,
        "request_id": request_id,
    }

    notified = await manager.send_to_host(room_id, host_id, join_notification)

    if not notified and cohost_id:
        notified = await manager.send_to_host(room_id, cohost_id, join_notification)

    if not notified:
        _pending_join_events.pop(user_id, None)
        await _send_rejected(websocket, "No host or cohost is currently connected.")
        return False

    # ── Wait for decision ──────────────────────────────────────────────────────
    try:
        await asyncio.wait_for(event.wait(), timeout=JOIN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        _pending_join_events.pop(user_id, None)
        await _send_rejected(websocket, "Join request timed out. Host did not respond.")
        return False

    _pending_join_events.pop(user_id, None)
    approved = result_container.get("approved", False)

    if not approved:
        await _send_rejected(websocket, "The host declined your request to join.")
        return False

    return True


async def handle_approval(msg: dict, room_id: str, approved: bool) -> None:
    """
    Host or cohost sent approve_user or reject_user.
    Persists the decision to PG and signals the waiting coroutine.
    """
    target_user_id = msg.get("target_user_id")
    request_id     = msg.get("request_id")

    if not target_user_id or not request_id:
        logger.warning(f"[Join] handle_approval missing fields: {msg}")
        return

    status = "approved" if approved else "rejected"
    try:
        async with db_conn.pool.acquire() as conn:
            await db_rooms.resolve_join_request(conn, request_id, status)
    except Exception as e:
        logger.error(f"[Join] resolve_join_request failed request={request_id}: {e}")

    # Signal the waiting run_join_flow coroutine
    entry = _pending_join_events.get(target_user_id)
    if entry:
        event, result_container = entry
        result_container["approved"] = approved
        event.set()
    else:
        logger.debug(
            f"[Join] approval signal for user={target_user_id} "
            f"but no pending event found (may have timed out)"
        )


async def _send_rejected(websocket: WebSocket, message: str) -> None:
    """Send JOIN_REJECTED and close the connection."""
    try:
        await websocket.send_text(json.dumps({
            "type":    MsgType.JOIN_REJECTED,
            "message": message,
        }))
        await websocket.close(code=4003)
    except Exception:
        pass  # socket may already be closing