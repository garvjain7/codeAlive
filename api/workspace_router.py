from fastapi import APIRouter, HTTPException, Request, Body
from db.connection import get_conn
from datetime import datetime, timedelta
import bcrypt
import uuid
from ot_collab.db import rooms as collab_db
from db.file_uploads import (
    get_user_file_uploads,
    delete_user_file_upload,
    update_user_file_password,
    update_user_file_expiry,
)
from services.file_service import get_r2_client

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
        total_files = await conn.fetchval("SELECT COUNT(*) FROM user_file_uploads WHERE owner_id = $1", uid)
        total_downloads = await conn.fetchval(
            "SELECT COALESCE(SUM(download_count), 0) FROM user_file_uploads WHERE owner_id = $1", uid
        )
        
        return {
            "total_snippets": total,
            "active_snippets": active,
            "unique_languages": langs,
            "accessed_count": accessed,
            "total_files": total_files,
            "total_downloads": total_downloads,
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


import logging
from core.config import ENABLE_ROOMS
logger = logging.getLogger(__name__)

@router.get("/workshops")
async def get_active_workshops(request: Request):
    """Return all active workshops the user can join or is hosting."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    if not ENABLE_ROOMS:
        return {"workshops": []}
        
    try:
        async with get_conn() as conn:
            workshops = await collab_db.get_active_workshops(conn, user_id)
            # Hydrate with member list for the UI
            for w in workshops:
                w["members"] = await collab_db.get_room_member_usernames(conn, str(w["room_id"]))
                
            return {"workshops": workshops}
    except Exception as e:
        logger.warning(f"Workshops query failed (optional module): {e}")
        return {"workshops": []}


# ── FILE MANAGEMENT ENDPOINTS ────────────────────────────────────────────────

@router.get("/files")
async def get_workspace_files(request: Request):
    """Return all files uploaded by the logged-in user."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        files = await get_user_file_uploads(conn, user_id)
        return {"files": files}


@router.delete("/files/{file_id}")
async def delete_workspace_file(file_id: str, request: Request):
    """Delete a user-owned file from R2 and the database."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        deleted = await delete_user_file_upload(conn, file_id, user_id)
        if not deleted:
            raise HTTPException(404, "File not found or unauthorized")

    # Remove from R2 storage (best-effort; don't fail if already gone)
    try:
        client, bucket_name = get_r2_client()
        client.delete_object(Bucket=bucket_name, Key=file_id)
    except Exception:
        pass  # Object may already be missing; DB deletion already succeeded

    return {"ok": True}


@router.patch("/files/{file_id}/password")
async def update_file_password(file_id: str, request: Request, payload: dict = Body(...)):
    """Set or update password protection on a user-owned file."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    password = payload.get("password")
    if not password:
        raise HTTPException(400, "Password is required")

    salt = bcrypt.gensalt()
    pwd_hash = bcrypt.hashpw(password.encode(), salt).decode()

    async with get_conn() as conn:
        updated = await update_user_file_password(conn, file_id, user_id, pwd_hash)
        if not updated:
            raise HTTPException(404, "File not found or unauthorized")

    return {"ok": True}


@router.patch("/files/{file_id}/expiry")
async def update_file_expiry(file_id: str, request: Request, payload: dict = Body(...)):
    """Extend the expiry of a user-owned file (capped at 90 days from creation)."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    days = payload.get("days")
    if not days or not isinstance(days, int) or days < 1:
        raise HTTPException(400, "Extension days (min 1) required")

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT created_at FROM user_file_uploads WHERE file_id = $1 AND owner_id = $2",
            file_id,
            uuid.UUID(user_id),
        )
        if not row:
            raise HTTPException(404, "File not found or unauthorized")

        created_at = row["created_at"]
        max_possible_expiry = created_at + timedelta(days=90)
        requested_expiry = datetime.now() + timedelta(days=days)
        final_expiry = min(max_possible_expiry, requested_expiry)

        if final_expiry <= datetime.now():
            raise HTTPException(400, "File has reached its maximum 90-day lifespan and cannot be extended further.")

        updated = await update_user_file_expiry(conn, file_id, user_id, final_expiry)
        if not updated:
            raise HTTPException(404, "File not found or unauthorized")

    return {
        "ok": True,
        "expires_at": final_expiry.isoformat(),
        "capped": final_expiry == max_possible_expiry,
    }


# ── BUNDLE MANAGEMENT ENDPOINTS ──────────────────────────────────────────────

from db.bundles import get_user_bundles, delete_bundle_by_code
from services.file_service import delete_uploaded_file

@router.get("/bundles")
async def get_workspace_bundles(request: Request):
    """Return all bundles owned by the logged-in user."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        bundles = await get_user_bundles(conn, uuid.UUID(user_id))
        return {"bundles": bundles}


@router.delete("/bundles/{code}")
async def delete_workspace_bundle(code: str, request: Request):
    """Delete a user-owned bundle and clean up R2 files if binary."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        success, r2_keys = await delete_bundle_by_code(conn, code, user_id)
        if not success:
            raise HTTPException(404, "Bundle not found or unauthorized")

    # Clean up R2 objects if binary bundle
    for r2_key in r2_keys:
        delete_uploaded_file(r2_key)

    return {"ok": True}

