from fastapi import APIRouter, HTTPException, Depends, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import bcrypt
import secrets
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import db.connection as db_conn
from db.users import get_user_by_identifier, get_user_by_id, create_user
from redis_client import async_redis
from mailer import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    identifier: str # can be email or username
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

def hash_password(password: str) -> str:
    # Use bcrypt for secure password hashing
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(password: str, hashed: str) -> bool:
    # Verify bcrypt hash
    return bcrypt.checkpw(password.encode(), hashed.encode())

async def create_session(response: Response, user_id: str):
    session_id = uuid.uuid4().hex
    # Store session for 2 hours (7200 seconds)
    await async_redis.setex(f"session:{session_id}", 7200, user_id)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=7200,
        secure=True
    )

@router.post("/signup")
async def signup(data: SignupRequest, response: Response):
    async with db_conn.pool.acquire() as conn:
        # Check if email is already taken
        if await get_user_by_identifier(conn, data.email):
            raise HTTPException(400, "Email already registered")
            
        # Check if username is already taken
        if await get_user_by_identifier(conn, data.username):
            raise HTTPException(400, "Username already taken")
            
        pwd_hash = hash_password(data.password)
        user = await create_user(conn, data.username, data.email, pwd_hash)
        
        await create_session(response, str(user["user_id"]))
        from utils import safe_log
        safe_log("User signed up successfully", {"username": data.username, "email": data.email})
        return {"ok": True, "user_id": str(user["user_id"])}

@router.post("/login")
async def login(data: LoginRequest, response: Response):
    async with db_conn.pool.acquire() as conn:
        user = await get_user_by_identifier(conn, data.identifier)
        if not user:
            from utils import safe_log
            safe_log("Failed login attempt - User not found", {"identifier": data.identifier})
            raise HTTPException(401, "Invalid credentials")
            
        if not verify_password(data.password, user["password_hash"]):
            from utils import safe_log
            safe_log("Failed login attempt - Wrong password", {"identifier": data.identifier})
            raise HTTPException(401, "Invalid credentials")
            
        await create_session(response, str(user["user_id"]))
        from utils import safe_log
        safe_log("User logged in successfully", {"user_id": str(user["user_id"]), "identifier": data.identifier})
        return {"ok": True, "user_id": str(user["user_id"])}

@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    """Request a password reset link."""
    async with db_conn.pool.acquire() as conn:
        # Look up user by email
        user = await get_user_by_identifier(conn, data.email)
        
        if user:
            # Generate secure token
            token = secrets.token_urlsafe(32)
            # Link expires in 20 minutes
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=20)
            
            # Store in database (hash the token for security)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            await conn.execute("""
                INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
            """, user["user_id"], token_hash, expires_at)
            
            # Send email
            send_password_reset_email(user["email"], token)
            
    # Always return success message for security
    return {"message": "If the email is correct, a reset link has been sent"}

@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    """Reset password using a valid token."""
    async with db_conn.pool.acquire() as conn:
        # Find active, non-expired token
        token_hash = hashlib.sha256(data.token.encode()).hexdigest()
        row = await conn.fetchrow("""
            SELECT user_id, id FROM password_reset_tokens
            WHERE token_hash = $1 AND used = FALSE AND expires_at > CURRENT_TIMESTAMP
        """, token_hash)
        
        if not row:
            raise HTTPException(400, "Invalid or expired token")
            
        # Hash new password with bcrypt
        pwd_hash = hash_password(data.new_password)
        
        # Update user password
        await conn.execute("""
            UPDATE users SET password_hash = $1 WHERE user_id = $2
        """, pwd_hash, row["user_id"])
        
        # Invalidate token
        await conn.execute("""
            UPDATE password_reset_tokens SET used = TRUE WHERE id = $1
        """, row["id"])
        
    return {"ok": True, "message": "Password updated successfully"}

@router.get("/logout")
async def logout(request: Request, response: Response):
    response.delete_cookie("session_id")
    return RedirectResponse(url="/")

@router.get("/me")
async def get_me(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    
    async with db_conn.pool.acquire() as conn:
        user = await get_user_by_id(conn, uuid.UUID(user_id))
        if not user:
            raise HTTPException(404, "User not found")
        
        return {
            "user_id": str(user["user_id"]),
            "username": user["username"],
            "email": user["email"]
        }
