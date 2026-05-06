from fastapi import APIRouter, HTTPException, Request
from db.connection import get_conn

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

@router.get("/created")
async def get_created_snippets(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT id, code_id, language, title, is_password_protected, expires_at, created_at
            FROM user_snippets
            WHERE owner_id = $1
            ORDER BY created_at DESC
        """, user_id)
        
        return {"snippets": [dict(r) for r in rows]}

@router.get("/accessed")
async def get_accessed_snippets(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    async with get_conn() as conn:
        # Section 2: Accessed protected snippets
        rows = await conn.fetch("""
            SELECT s.id, s.code_id, s.language, s.title, s.expires_at, s.created_at, a.first_success_at
            FROM user_snippets s
            JOIN snippet_access_control a ON s.id = a.snippet_id
            WHERE a.user_id = $1 AND a.first_success_at IS NOT NULL
            ORDER BY a.first_success_at DESC
        """, user_id)
        
        return {"snippets": [dict(r) for r in rows]}

@router.get("/stats")
async def get_workspace_stats(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    async with get_conn() as conn:
        # Total snippets
        total = await conn.fetchval("SELECT COUNT(*) FROM user_snippets WHERE owner_id = $1", user_id)
        
        # Active snippets (not expired)
        active = await conn.fetchval("SELECT COUNT(*) FROM user_snippets WHERE owner_id = $1 AND expires_at > NOW()", user_id)
        
        # Unique languages
        langs = await conn.fetchval("SELECT COUNT(DISTINCT language) FROM user_snippets WHERE owner_id = $1", user_id)
        
        # Accessed protected snippets
        accessed = await conn.fetchval("""
            SELECT COUNT(*) FROM snippet_access_control 
            WHERE user_id = $1 AND first_success_at IS NOT NULL
        """, user_id)
        
        return {
            "total_snippets": total,
            "active_snippets": active,
            "unique_languages": langs,
            "accessed_count": accessed
        }
