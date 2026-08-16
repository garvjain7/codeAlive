"""
ot_collab/bundle_ws_router.py
------------------------------
WebSocket router for Bundle Text File real-time OT collaboration.
Allows multiple logged-in users to edit a bundle text file simultaneously.
"""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import db.connection as db_conn
from db.users import get_user_by_id
import db.bundles as db_bundles
from core.redis_client import async_redis
from core.utils import compress_code, decompress_code

from .models import (
    Op, OpType, MsgType,
    ClientOpMessage, CursorMessage,
    assign_color
)
from . import ot_engine, room_state
from .connection_manager import manager
from .handlers import handle_op, handle_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collab", tags=["bundle_collaboration"])


async def _auth_websocket(session_id: Optional[str]) -> Optional[str]:
    if not session_id:
        return None
    return await async_redis.get(f"session:{session_id}")


async def _get_username(user_id: str) -> str:
    try:
        async with db_conn.pool.acquire() as conn:
            user = await get_user_by_id(conn, uuid.UUID(user_id))
            if user:
                return user["username"]
    except Exception:
        pass
    return user_id[:8]


async def _flush_bundle_file_to_postgres(file_identifier: str, last_edited_by: Optional[str] = None):
    """Flush latest raw text from Redis to Postgres in compressed form."""
    room_id = f"bundle_file:{file_identifier}"
    try:
        content, _ = await room_state.get_room_doc(room_id)
        encoded = compress_code(content or "")
        async with db_conn.pool.acquire() as conn:
            await db_bundles.flush_bundle_text_file(
                conn,
                file_identifier=file_identifier,
                encoded_content=encoded,
                last_edited_by=uuid.UUID(last_edited_by) if last_edited_by else None
            )
    except Exception as e:
        logger.warning(f"[BundleWS] Flush failed for file_identifier={file_identifier}: {e}")


@router.websocket("/ws/bundle-file/{file_id}")
async def bundle_file_websocket_endpoint(
    websocket: WebSocket,
    file_id: str,
    session_id: Optional[str] = Query(None)
):
    await websocket.accept()

    # 1. Auth check
    user_id = await _auth_websocket(session_id)
    if not user_id:
        await websocket.send_text(json.dumps({
            "type": MsgType.ERROR,
            "code": "auth_failed",
            "message": "Login required"
        }))
        await websocket.close(code=4001)
        return

    username = await _get_username(user_id)

    # 2. Database & Permission Validation
    async with db_conn.pool.acquire() as conn:
        file_row = await conn.fetchrow(
            """
            SELECT btf.id, btf.bundle_id, btf.code AS file_code, btf.name, btf.encoded_content,
                   b.code AS bundle_code, b.owner_id, b.permission, b.bundle_type
            FROM bundle_text_files btf
            JOIN bundles b ON b.id = btf.bundle_id
            WHERE btf.code = $1 OR btf.id::text = $1
            """,
            file_id
        )

    if not file_row:
        await websocket.send_text(json.dumps({
            "type": MsgType.ERROR,
            "code": "file_not_found",
            "message": "Bundle text file not found"
        }))
        await websocket.close(code=4004)
        return

    if file_row["bundle_type"] != "text":
        await websocket.send_text(json.dumps({
            "type": MsgType.ERROR,
            "code": "binary_file_not_editable",
            "message": "Binary files cannot be edited via OT collaboration"
        }))
        await websocket.close(code=4003)
        return

    # Standardize room_id to canonical UUID string so all clients edit same Redis room
    canonical_file_id = str(file_row["id"])
    room_id = f"bundle_file:{canonical_file_id}"

    is_owner = (str(file_row["owner_id"]) == user_id)
    permission = file_row["permission"]

    can_edit = is_owner or (permission == "anyone")
    role = "host" if is_owner else "participant"

    # 3. Warm Redis document if cold (decompress encoded_content)
    if not await room_state.room_exists_in_redis(room_id):
        raw_content = ""
        if file_row["encoded_content"]:
            try:
                raw_content = decompress_code(file_row["encoded_content"])
            except Exception as e:
                logger.error(f"[BundleWS] Decompression failed for file_id={file_id}: {e}")
                raw_content = ""

        await room_state.init_document(
            room_id=room_id,
            content=raw_content,
            revision=0
        )

    content, revision = await room_state.get_room_doc(room_id)

    # 4. Presence
    existing_colors = await room_state.get_existing_colors(room_id)
    color = assign_color(existing_colors)
    await room_state.add_user_to_room(room_id, user_id, username, color, role=role, is_muted=False)
    manager.connect(room_id, user_id, websocket)

    # Send Join Approved
    room_users = await room_state.get_room_users(room_id)
    users_list = [
        {"user_id": uid, "username": d["username"], "color": d["color"], "role": d["role"], "is_muted": False}
        for uid, d in room_users.items()
    ]

    await websocket.send_text(json.dumps({
        "type": MsgType.JOIN_APPROVED,
        "content": content,
        "revision": revision,
        "users": users_list,
        "your_role": role,
        "can_edit": can_edit
    }))

    await manager.broadcast(room_id, {
        "type": MsgType.PARTICIPANT_JOINED,
        "user_id": user_id,
        "username": username,
        "color": color,
        "role": role,
    }, exclude_user_id=user_id)

    # 5. Relay Loop
    class ImmediateBackgroundTasks:
        def add_task(self, func, *args, **kwargs):
            asyncio.create_task(func(*args, **kwargs))
            
    background = ImmediateBackgroundTasks()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == MsgType.OP:
                if not can_edit:
                    await websocket.send_text(json.dumps({
                        "type": MsgType.ERROR,
                        "code": "permission_denied",
                        "message": "ReadOnly mode. Only authorized users can edit this bundle."
                    }))
                    continue
                await handle_op(websocket, msg, room_id, user_id, background)
            elif mtype == MsgType.CURSOR:
                await handle_cursor(msg, room_id, user_id)

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(room_id, user_id)
        await room_state.remove_user_from_room(room_id, user_id)
        
        await manager.broadcast(room_id, {
            "type": MsgType.PARTICIPANT_LEFT,
            "user_id": user_id
        }, exclude_user_id=user_id)

        # On last user exit: flush final compressed content to Postgres and teardown Redis room state
        if manager.get_connection_count(room_id) == 0:
            await _flush_bundle_file_to_postgres(canonical_file_id, last_edited_by=user_id)
            await room_state.expire_document_keys(room_id)
