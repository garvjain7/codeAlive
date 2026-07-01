"""
api/collab_router.py
--------------------
Stateless HTTP endpoints for workshop management and discovery.
Isolates administrative logic from real-time WebSocket relaying.
"""

from __future__ import annotations
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

import db.connection as db_conn
from core.redis_client import async_redis
from services.mail_service_v2 import send_workshop_invitation

# Import from ot_collab package
from ot_collab import room_state
from ot_collab.db import rooms as db_rooms
from ot_collab.connection_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collab", tags=["collaboration"])

# ── Models ────────────────────────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    title:    str
    password: Optional[str] = None

class InviteRequest(BaseModel):
    emails: List[EmailStr]

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/rooms")
async def create_room(body: CreateRoomRequest, request: Request):
    """Create a new workshop room."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    if not body.title or not body.title.strip():
        raise HTTPException(400, "Title required")

    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.create_room(conn, user_id, body.title.strip())
        room_id = str(room["room_id"])

        if body.password:
            from ot_collab.password_utils import hash_password
            hashed = hash_password(body.password)
            await db_rooms.set_room_password(conn, room_id, hashed)

    # Initialize in Redis
    await room_state.init_room_in_redis(
        room_id=room_id,
        content="",
        revision=0,
        host_id=user_id,
    )

    return {
        "room_id":      room_id,
        "title":        room["title"],
        "has_password": bool(body.password)
    }


@router.get("/rooms/{room_id}")
async def get_room_info(room_id: str, request: Request):
    """Fetch room metadata and active member count."""
    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.get_room(conn, room_id)
        if not room:
            raise HTTPException(404, "Room not found")
        
    connected_count = manager.get_connection_count(room_id)

    return {
        "room_id":           str(room["room_id"]),
        "title":             room["title"],
        "host_id":           str(room["host_id"]),
        "is_active":         room["is_active"],
        "has_password":      bool(room["password_hash"]),
        "connected_count":   connected_count,
        "created_at":        room["created_at"].isoformat(),
    }


@router.get("/active")
async def get_active_workshops(request: Request):
    """Return live workshops for the current user's dashboard."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    async with db_conn.pool.acquire() as conn:
        workshops = await db_rooms.get_active_workshops(conn, user_id)
        # Add live member lists
        for w in workshops:
            w["members"] = await db_rooms.get_room_member_usernames(conn, str(w["room_id"]))
            w["connected_count"] = manager.get_connection_count(str(w["room_id"]))
            
        return {"workshops": workshops}


@router.post("/rooms/{room_id}/invite")
async def invite_to_workshop(room_id: str, body: InviteRequest, request: Request):
    """Invite users to a workshop via email."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with db_conn.pool.acquire() as conn:
        room = await db_rooms.get_room(conn, room_id)
        if not room:
            raise HTTPException(404, "Room not found")
        
        if str(room["host_id"]) != user_id and str(room.get("cohost_id")) != user_id:
            raise HTTPException(403, "Permission denied")

        success_count = 0
        room_url = f"{request.base_url}workshop/{room_id}"
        host_name = getattr(request.state, "username", "A CodeAlive user")
        
        for email in body.emails:
            if send_workshop_invitation(email, room["title"], room_url, host_name):
                success_count += 1

    return {"ok": True, "sent_count": success_count}
