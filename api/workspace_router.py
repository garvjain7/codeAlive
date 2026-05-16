from fastapi import APIRouter, HTTPException, Request, Body
from db.connection import get_conn
from datetime import datetime, timedelta
import bcrypt
import uuid

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
        """, uuid.UUID(user_id))
        
        return {"snippets": [dict(r) for r in rows]}

@router.get("/accessed")
async def get_accessed_snippets(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT s.id, s.code_id, s.language, s.title, s.expires_at, s.created_at, a.first_success_at
            FROM user_snippets s
            JOIN snippet_access_control a ON s.id = a.snippet_id
            WHERE a.user_id = $1 AND a.first_success_at IS NOT NULL
            ORDER BY a.first_success_at DESC
        """, uuid.UUID(user_id))
        
        return {"snippets": [dict(r) for r in rows]}

@router.get("/stats")
async def get_workspace_stats(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    async with get_conn() as conn:
        uid = uuid.UUID(user_id)
        total = await conn.fetchval("SELECT COUNT(*) FROM user_snippets WHERE owner_id = $1", uid)
        active = await conn.fetchval("SELECT COUNT(*) FROM user_snippets WHERE owner_id = $1 AND expires_at > NOW()", uid)
        langs = await conn.fetchval("SELECT COUNT(DISTINCT language) FROM user_snippets WHERE owner_id = $1", uid)
        accessed = await conn.fetchval("""
            SELECT COUNT(*) FROM snippet_access_control 
            WHERE user_id = $1 AND first_success_at IS NOT NULL
        """, uid)
        
        return {
            "total_snippets": total,
            "active_snippets": active,
            "unique_languages": langs,
            "accessed_count": accessed
        }

@router.delete("/snippets/{code_id}")
async def delete_snippet(code_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    async with get_conn() as conn:
        res = await conn.execute("""
            DELETE FROM user_snippets 
            WHERE code_id = $1 AND owner_id = $2
        """, code_id, uuid.UUID(user_id))
        
        if res == "DELETE 0":
            raise HTTPException(404, "Snippet not found or unauthorized")
            
        return {"ok": True}

@router.patch("/snippets/{code_id}/password")
async def update_snippet_password(code_id: str, request: Request, payload: dict = Body(...)):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    password = payload.get("password")
    if not password:
        raise HTTPException(400, "Password is required")
        
    salt = bcrypt.gensalt()
    pwd_hash = bcrypt.hashpw(password.encode(), salt).decode()
    
    async with get_conn() as conn:
        res = await conn.execute("""
            UPDATE user_snippets 
            SET is_password_protected = TRUE, password_hash = $1
            WHERE code_id = $2 AND owner_id = $3
        """, pwd_hash, code_id, uuid.UUID(user_id))
        
        if res == "UPDATE 0":
            raise HTTPException(404, "Snippet not found or unauthorized")
            
        # Reset any existing access control for this snippet so everyone must re-verify
        await conn.execute("DELETE FROM snippet_access_control WHERE snippet_id = (SELECT id FROM user_snippets WHERE code_id = $1)", code_id)
            
        return {"ok": True}

@router.patch("/snippets/{code_id}/expiry")
async def update_snippet_expiry(code_id: str, request: Request, payload: dict = Body(...)):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    days = payload.get("days")
    if not days or not isinstance(days, int) or days < 1:
        raise HTTPException(400, "Extension days (min 1) required")
        
    async with get_conn() as conn:
        uid = uuid.UUID(user_id)
        # 1. Fetch current creation date to enforce the 90-day hard limit
        snippet = await conn.fetchrow("""
            SELECT created_at, expires_at 
            FROM user_snippets 
            WHERE code_id = $1 AND owner_id = $2
        """, code_id, uid)
        
        if not snippet:
            raise HTTPException(404, "Snippet not found or unauthorized")
            
        created_at = snippet["created_at"]
        
        # 2. Logic: Max expiry is exactly 90 days from CREATION
        max_possible_expiry = created_at + timedelta(days=90)
        requested_expiry = datetime.now() + timedelta(days=days)
        
        # Cap the expiry at the 90-day mark
        final_expiry = min(max_possible_expiry, requested_expiry)
        
        if final_expiry <= datetime.now():
            raise HTTPException(400, "Snippet has reached its maximum 90-day lifespan and cannot be extended further.")
            
        await conn.execute("""
            UPDATE user_snippets 
            SET expires_at = $1 
            WHERE code_id = $2 AND owner_id = $3
        """, final_expiry, code_id, uid)
            
        return {
            "ok": True, 
            "expires_at": final_expiry.isoformat(),
            "capped": final_expiry == max_possible_expiry
        }

