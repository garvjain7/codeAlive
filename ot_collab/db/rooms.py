"""
ot_collab/db/rooms.py
---------------------
PostgreSQL queries for rooms, participants, and join requests.

Pattern matches existing codebase:
  - asyncpg conn passed in, no pool management here
  - dict(row) if row else None
  - raw parameterized SQL
  - UUID types passed as uuid.UUID objects
"""

from __future__ import annotations
import uuid
from typing import Optional


# ── Rooms ─────────────────────────────────────────────────────────────────────

async def create_room(conn, host_id: str, title: str) -> dict:
    """Create a new room. Returns the full room row."""
    row = await conn.fetchrow("""
        INSERT INTO rooms (host_id, title)
        VALUES ($1, $2)
        RETURNING *
    """, uuid.UUID(host_id), title)
    return dict(row)


async def get_room(conn, room_id: str) -> Optional[dict]:
    """Fetch room by room_id. Returns None if not found."""
    row = await conn.fetchrow("""
        SELECT * FROM rooms WHERE room_id = $1
    """, uuid.UUID(room_id))
    return dict(row) if row else None


async def set_room_inactive(conn, room_id: str) -> None:
    """Mark room as closed. Called when host closes the room."""
    await conn.execute("""
        UPDATE rooms
        SET is_active = FALSE, last_active_at = NOW()
        WHERE room_id = $1
    """, uuid.UUID(room_id))


async def update_room_revision(conn, room_id: str, revision: int) -> None:
    """
    Sync PostgreSQL current_revision with Redis.
    Called on snapshot write so PG stays consistent with Redis.
    """
    await conn.execute("""
        UPDATE rooms
        SET current_revision = $1, last_active_at = NOW()
        WHERE room_id = $2
    """, revision, uuid.UUID(room_id))


# ── Participants ───────────────────────────────────────────────────────────────

async def add_participant(conn, room_id: str, user_id: str, role: str = 'participant') -> None:
    """
    Add a user as an approved participant.
    ON CONFLICT DO NOTHING makes this safe to call on reconnect —
    the UNIQUE(room_id, user_id) constraint prevents duplicates.
    """
    await conn.execute("""
        INSERT INTO room_participants (room_id, user_id, role)
        VALUES ($1, $2, $3)
        ON CONFLICT (room_id, user_id) DO NOTHING
    """, uuid.UUID(room_id), uuid.UUID(user_id), role)


async def get_participant(conn, room_id: str, user_id: str) -> Optional[dict]:
    """Fetch participant details (role, is_muted) by room and user."""
    row = await conn.fetchrow("""
        SELECT * FROM room_participants
        WHERE room_id = $1 AND user_id = $2
    """, uuid.UUID(room_id), uuid.UUID(user_id))
    return dict(row) if row else None


async def set_participant_muted(conn, room_id: str, user_id: str, is_muted: bool) -> None:
    """Update a participant's muted status."""
    await conn.execute("""
        UPDATE room_participants
        SET is_muted = $1
        WHERE room_id = $2 AND user_id = $3
    """, is_muted, uuid.UUID(room_id), uuid.UUID(user_id))


async def is_participant(conn, room_id: str, user_id: str) -> bool:
    """Check if user is an approved participant of this room."""
    row = await conn.fetchrow("""
        SELECT 1 FROM room_participants
        WHERE room_id = $1 AND user_id = $2
    """, uuid.UUID(room_id), uuid.UUID(user_id))
    return row is not None


async def get_participants(conn, room_id: str) -> list[dict]:
    """Return all participants with user info, role, and mute state."""
    rows = await conn.fetch("""
        SELECT rp.user_id, u.username, rp.role, rp.is_muted, rp.joined_at
        FROM room_participants rp
        JOIN users u ON u.user_id = rp.user_id
        WHERE rp.room_id = $1
        ORDER BY rp.joined_at ASC
    """, uuid.UUID(room_id))
    return [dict(r) for r in rows]


# ── Join requests ─────────────────────────────────────────────────────────────

async def create_join_request(conn, room_id: str, user_id: str) -> dict:
    """
    Insert a new join request.
    If user already has a pending request, return the existing one.
    If user was previously rejected, insert a new request.
    """
    # Check for existing pending request first
    existing = await conn.fetchrow("""
        SELECT * FROM room_join_requests
        WHERE room_id = $1 AND user_id = $2 AND status = 'pending'
    """, uuid.UUID(room_id), uuid.UUID(user_id))
    if existing:
        return dict(existing)

    row = await conn.fetchrow("""
        INSERT INTO room_join_requests (room_id, user_id)
        VALUES ($1, $2)
        RETURNING *
    """, uuid.UUID(room_id), uuid.UUID(user_id))
    return dict(row)


async def resolve_join_request(
    conn,
    request_id: str,
    status: str,        # 'approved' | 'rejected'
) -> None:
    """Mark a join request as resolved."""
    await conn.execute("""
        UPDATE room_join_requests
        SET status = $1, resolved_at = NOW()
        WHERE id = $2
    """, status, uuid.UUID(request_id))


async def get_pending_request(
    conn,
    room_id: str,
    user_id: str,
) -> Optional[dict]:
    """Get the active pending request for a user in a room, if any."""
    row = await conn.fetchrow("""
        SELECT * FROM room_join_requests
        WHERE room_id = $1 AND user_id = $2 AND status = 'pending'
        ORDER BY requested_at DESC
        LIMIT 1
    """, uuid.UUID(room_id), uuid.UUID(user_id))
    return dict(row) if row else None


# ── Room Configuration ────────────────────────────────────────────────────────

async def set_cohost(conn, room_id: str, user_id: str) -> None:
    """Set the cohost for a room."""
    await conn.execute("""
        UPDATE rooms SET cohost_id = $1 WHERE room_id = $2
    """, uuid.UUID(user_id), uuid.UUID(room_id))
    
    # Also update their role in the participants table
    await conn.execute("""
        UPDATE room_participants SET role = 'cohost'
        WHERE room_id = $1 AND user_id = $2
    """, uuid.UUID(room_id), uuid.UUID(user_id))


async def clear_cohost(conn, room_id: str, user_id: str) -> None:
    """Remove cohost status from a user."""
    await conn.execute("""
        UPDATE rooms SET cohost_id = NULL WHERE room_id = $1 AND cohost_id = $2
    """, uuid.UUID(room_id), uuid.UUID(user_id))
    
    await conn.execute("""
        UPDATE room_participants SET role = 'participant'
        WHERE room_id = $1 AND user_id = $2
    """, uuid.UUID(room_id), uuid.UUID(user_id))


async def set_room_locked(conn, room_id: str, locked: bool) -> None:
    """Toggle room lock status."""
    await conn.execute("""
        UPDATE rooms SET is_locked = $1 WHERE room_id = $2
    """, locked, uuid.UUID(room_id))


async def set_room_password(conn, room_id: str, password_hash: Optional[str]) -> int:
    """
    Set or clear the room password.
    Increments password_version and returns the new value.
    """
    row = await conn.fetchrow("""
        UPDATE rooms
        SET password_hash = $1, 
            password_version = password_version + 1,
            last_active_at = NOW()
        WHERE room_id = $2
        RETURNING password_version
    """, password_hash, uuid.UUID(room_id))
    return row["password_version"]