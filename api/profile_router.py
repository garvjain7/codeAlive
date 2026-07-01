from fastapi import APIRouter, HTTPException, Request
from db.connection import get_conn
import uuid
from ot_collab.db import rooms as collab_db

router = APIRouter(prefix="/api/profile", tags=["profile"])

@router.get("/summary")
async def get_profile_summary(request: Request):
    user_id_raw = getattr(request.state, "user_id", None)
    if not user_id_raw:
        raise HTTPException(401, "Login required")
    
    user_id = uuid.UUID(user_id_raw)
        
    async with get_conn() as conn:
        # 1. User Info
        user = await conn.fetchrow("SELECT username, email, created_at FROM users WHERE user_id = $1", user_id)
        if not user:
            raise HTTPException(404, "User not found")
        
        # 2. Stats
        total = await conn.fetchval("SELECT COUNT(*) FROM user_snippets WHERE owner_id = $1", user_id)
        protected = await conn.fetchval("SELECT COUNT(*) FROM user_snippets WHERE owner_id = $1 AND is_password_protected = TRUE", user_id)
        langs_count = await conn.fetchval("SELECT COUNT(DISTINCT language) FROM user_snippets WHERE owner_id = $1", user_id)
        room_count = await conn.fetchval("SELECT COUNT(*) FROM rooms WHERE host_id = $1", user_id)
        
        # 3. Language Distribution
        lang_rows = await conn.fetch("""
            SELECT language, COUNT(*) as count
            FROM user_snippets
            WHERE owner_id = $1
            GROUP BY language
            ORDER BY count DESC
        """, user_id)
        
        total_count = sum(r["count"] for r in lang_rows) if lang_rows else 0
        lang_dist = []
        for r in lang_rows:
            lang_dist.append({
                "language": r["language"] or "text",
                "count": r["count"],
                "percentage": round((r["count"] / total_count) * 100) if total_count > 0 else 0
            })
            
        # 4. Recent Snippets (Top 5)
        recent_rows = await conn.fetch("""
            SELECT code_id, language, title, is_password_protected, created_at
            FROM user_snippets
            WHERE owner_id = $1
            ORDER BY created_at DESC
            LIMIT 5
        """, user_id)
        
        return {
            "user": {
                "username": user["username"],
                "email": user["email"],
                "joined_at": user["created_at"].isoformat()
            },
            "stats": {
                "total": total,
                "protected": protected,
                "languages": langs_count,
                "rooms": room_count
            },
            "languages": lang_dist,
            "recent": [dict(r) for r in recent_rows]
        }


@router.get("/collab-history")
async def get_collab_history(request: Request):
    """Return history of all workshops created by the user."""
    user_id_raw = getattr(request.state, "user_id", None)
    if not user_id_raw:
        raise HTTPException(401, "Login required")
        
    async with get_conn() as conn:
        history = await collab_db.get_user_room_history(conn, user_id_raw)
        return {"history": history}
