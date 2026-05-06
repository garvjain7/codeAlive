from fastapi import APIRouter, HTTPException, Request, Form
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
from db.connection import get_conn
from db.snippets import create_anonymous, create_user_snippet, get_snippet_by_code_id
from db.access_control import get_or_create_access, increment_failed_attempt, mark_success
from utils import validate_code, generate_id, compress_code

router = APIRouter(prefix="/api/snippets", tags=["snippets"])

_RESERVED = frozenset({"editor", "waitlist", "static", "s", "new", "robots.txt", "sitemap.xml", "api"})

class AnonymousSnippetCreate(BaseModel):
    code: str
    language: str = "text"
    highlights: str = ""
    custom_code: Optional[str] = None

class UserSnippetCreate(BaseModel):
    code: str
    language: str = "text"
    highlights: str = ""
    custom_code: Optional[str] = None
    title: str
    password: Optional[str] = None
    expires_in_days: int = 30

class SnippetVerify(BaseModel):
    password: str

import bcrypt

def hash_password(password: str) -> str:
    # Use bcrypt for secure password hashing
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(password: str, hashed: str) -> bool:
    # Verify bcrypt hash
    return bcrypt.checkpw(password.encode(), hashed.encode())

async def resolve_code_id(conn, custom_code: Optional[str]) -> str:
    if custom_code:
        custom_code = custom_code.strip()
        if not custom_code:
            raise HTTPException(400, "Custom code cannot be empty")
        if len(custom_code) > 30:
            raise HTTPException(400, "Custom code too long (max 30 chars)")
        if custom_code in _RESERVED:
            raise HTTPException(400, "That slug is reserved — pick another")
        
        # Check if exists
        existing = await get_snippet_by_code_id(conn, custom_code)
        if existing:
            raise HTTPException(400, "Custom code already taken")
        return custom_code
    
    # Generate random
    while True:
        code_id = generate_id()
        existing = await get_snippet_by_code_id(conn, code_id)
        if not existing:
            return code_id

@router.post("/anonymous")
async def create_anon(data: AnonymousSnippetCreate):
    validate_code(data.code)
    
    async with get_conn() as conn:
        code_id = await resolve_code_id(conn, data.custom_code)
        
        await create_anonymous(
            conn,
            code_id=code_id,
            encoded_content=compress_code(data.code),
            language=data.language or "text",
            highlights=data.highlights or ""
        )
        return {"url": f"/s/{code_id}", "code_id": code_id}

@router.post("/user")
async def create_user(data: UserSnippetCreate, request: Request):
    owner_id = getattr(request.state, "user_id", None) 
    if not owner_id:
        raise HTTPException(status_code=401, detail="Unauthorized. Session invalid or expired.")
        
    validate_code(data.code)
    
    if data.expires_in_days < 1 or data.expires_in_days > 90:
        raise HTTPException(400, "Expiry must be between 1 and 90 days")
        
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)
    
    async with get_conn() as conn:
        code_id = await resolve_code_id(conn, data.custom_code)
        
        pwd_hash = hash_password(data.password) if data.password else None
        
        # Since auth is step 5, let's just make owner_id optional for this step testing or use a dummy UUID
        # We will use None for now if not authenticated.
        
        await create_user_snippet(
            conn,
            code_id=code_id,
            owner_id=owner_id,
            encoded_content=compress_code(data.code),
            language=data.language or "text",
            highlights=data.highlights or "",
            password_hash=pwd_hash,
            expires_at=expires_at.replace(tzinfo=None), # asyncpg often handles naive datetime natively
            title=data.title
        )
        return {"url": f"/s/{code_id}", "code_id": code_id}


@router.get("/{code_id}")
async def get_snippet(code_id: str, request: Request):
    async with get_conn() as conn:
        snippet = await get_snippet_by_code_id(conn, code_id)
        if not snippet:
            raise HTTPException(404, "Snippet not found")
            
        if snippet["type"] == "anonymous":
            return {"snippet": snippet}
            
        # User snippet logic
        if snippet["expires_at"] < datetime.now(): # tz aware vs naive
            raise HTTPException(404, "Snippet has expired")
            
        if snippet["is_password_protected"]:
            # Need login context
            user_id = getattr(request.state, "user_id", None)
            if not user_id:
                raise HTTPException(401, "Login required to access this snippet")
                
            # Check access control
            access = await get_or_create_access(conn, snippet["id"], user_id)
            
            if access.get("locked_until") and access["locked_until"] > datetime.now():
                raise HTTPException(403, "Access locked due to too many failed attempts")
                
            # If not successfully accessed yet, require verify
            if not access.get("first_success_at"):
                raise HTTPException(403, "Password required", headers={"X-Requires-Password": "true"})
                
        return {"snippet": snippet}

@router.post("/{code_id}/verify")
async def verify_snippet(code_id: str, data: SnippetVerify, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")
        
    async with get_conn() as conn:
        snippet = await get_snippet_by_code_id(conn, code_id)
        if not snippet or snippet["type"] != "user":
            raise HTTPException(404, "Snippet not found")
            
        if not snippet["is_password_protected"]:
            return {"ok": True}
            
        access = await get_or_create_access(conn, snippet["id"], user_id)
        
        if access.get("locked_until") and access["locked_until"] > datetime.now():
            raise HTTPException(403, "Access locked. Try again later.")
            
        if not verify_password(data.password, snippet["password_hash"]):
            await increment_failed_attempt(conn, snippet["id"], user_id)
            raise HTTPException(401, "Invalid password")
            
        await mark_success(conn, snippet["id"], user_id)
        return {"ok": True, "message": "Access granted"}

