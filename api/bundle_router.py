from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
import uuid
import os
from datetime import datetime, timedelta

from db.connection import get_conn
import db.bundles as db_bundles
from core.utils import generate_id, compress_code, decompress_code
from services.language_detector import detect_language
from services.file_service import validate_upload_file, save_uploaded_file, delete_uploaded_file
from ot_collab.password_utils import hash_password, verify_password
from core.redis_client import async_redis
from ot_collab import room_state

router = APIRouter(tags=["bundles"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


class InitialTextFileInput(BaseModel):
    name: Optional[str] = "untitled-1"
    content: Optional[str] = ""
    language: Optional[str] = None
    password: Optional[str] = None


class CreateTextBundleRequest(BaseModel):
    title: Optional[str] = None
    permission: Optional[str] = "admin_only"
    password: Optional[str] = None
    expires_in_days: Optional[int] = 30
    files: Optional[List[InitialTextFileInput]] = None


class RenameFileRequest(BaseModel):
    name: str
    language: Optional[str] = None


class UpdatePermissionRequest(BaseModel):
    permission: str


class AddTextFileRequest(BaseModel):
    name: Optional[str] = "untitled"
    content: Optional[str] = ""
    language: Optional[str] = None
    password: Optional[str] = None


class VerifyPasswordRequest(BaseModel):
    password: str


@router.post("/bundle/text")
async def create_text_bundle(request: Request, payload: CreateTextBundleRequest):
    """
    Create a new text/code bundle (logged-in users only).
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    files_input = payload.files or [InitialTextFileInput()]
    if len(files_input) > 5:
        raise HTTPException(400, "A bundle can have at most 5 initial files")

    code = generate_id()
    pwd_hash = hash_password(payload.password) if payload.password else None
    expires_at = datetime.utcnow() + timedelta(days=payload.expires_in_days or 30) if payload.expires_in_days else None

    async with get_conn() as conn:
        bundle = await db_bundles.create_bundle(
            conn,
            owner_id=uuid.UUID(user_id),
            code=code,
            bundle_type="text",
            title=payload.title,
            permission=payload.permission or "admin_only",
            expires_at=expires_at,
            password_hash=pwd_hash,
        )

        for f in files_input:
            content_str = f.content or ""
            lang = f.language or (detect_language(content_str) if content_str else "text")
            file_pwd_hash = hash_password(f.password) if f.password else None
            
            # Compress content for storage
            encoded = compress_code(content_str)

            # Insert initial file directly into bundle_text_files
            await db_bundles.add_bundle_text_file(
                conn,
                bundle_id=bundle["id"],
                name=f.name or "untitled",
                language=lang,
                password_hash=file_pwd_hash,
            )
            # Flush initial encoded content
            text_files = await conn.fetch(
                "SELECT id FROM bundle_text_files WHERE bundle_id = $1 ORDER BY position DESC LIMIT 1",
                bundle["id"]
            )
            if text_files:
                await db_bundles.flush_bundle_text_file(
                    conn,
                    file_id=text_files[0]["id"],
                    encoded_content=encoded,
                    last_edited_by=uuid.UUID(user_id)
                )

        full_bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        return {"ok": True, "code": code, "url": f"/b/{code}", "bundle": full_bundle}


@router.post("/bundle/binary")
async def create_binary_bundle(
    request: Request,
    title: Optional[str] = Form(None),
    permission: Optional[str] = Form("admin_only"),
    password: Optional[str] = Form(None),
    expires_in_days: Optional[int] = Form(30),
    file: UploadFile = File(...),
):
    """
    Create a new binary bundle with an initial binary file (logged-in users only).
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(400, "Empty file upload is not allowed")

    validation = validate_upload_file(file.filename or "", len(raw_bytes), file.content_type)
    if not validation["ok"]:
        raise HTTPException(400, validation["error"])

    if validation.get("is_text"):
        raise HTTPException(400, "Cannot upload a text file to create a binary bundle. Use text bundle route instead.")

    code = generate_id()
    pwd_hash = hash_password(password) if password else None
    expires_at = datetime.utcnow() + timedelta(days=expires_in_days or 30) if expires_in_days else None

    async with get_conn() as conn:
        bundle = await db_bundles.create_bundle(
            conn,
            owner_id=uuid.UUID(user_id),
            code=code,
            bundle_type="binary",
            title=title,
            permission=permission or "admin_only",
            expires_at=expires_at,
            password_hash=pwd_hash,
        )

        r2_file_id = generate_id()
        saved_file = save_uploaded_file(
            file_id=r2_file_id,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            content=raw_bytes,
        )

        await db_bundles.add_bundle_binary_file(
            conn,
            bundle_id=bundle["id"],
            file_id=r2_file_id,
            name=file.filename or "untitled",
            original_filename=file.filename or "upload",
            file_type=validation.get("extension") or "bin",
            file_size_bytes=len(raw_bytes),
            password_hash=None,
        )

        full_bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        return {"ok": True, "code": code, "url": f"/b/{code}", "bundle": full_bundle}


@router.get("/b/{code}", response_class=HTMLResponse)
async def view_bundle_page(request: Request, code: str):
    """
    Serve the bundle HTML page for logged-in users.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return RedirectResponse(url=f"/login?next=/b/{code}")

    async with get_conn() as conn:
        bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not bundle:
            raise HTTPException(404, "Bundle not found")

        # Check bundle-level password protection
        if bundle.get("is_password_protected") and str(bundle["owner_id"]) != user_id:
            access = await db_bundles.get_or_create_bundle_access(conn, bundle["id"], uuid.UUID(user_id))
            if access.get("locked_until") and access["locked_until"] > datetime.utcnow():
                raise HTTPException(403, "Too many failed password attempts. Try again later.")

        # Include both encoded_content and decompressed content for text files
        if bundle["bundle_type"] == "text" and bundle.get("files"):
            for f in bundle["files"]:
                full_f = await db_bundles.get_bundle_text_file(conn, f["id"])
                if full_f and full_f.get("encoded_content"):
                    f["encoded_content"] = full_f["encoded_content"]
                    try:
                        f["content"] = decompress_code(full_f["encoded_content"])
                    except Exception:
                        f["content"] = ""
                else:
                    f["encoded_content"] = ""
                    f["content"] = ""

        template_name = "bundle.html" if os.path.exists(os.path.join(BASE_DIR, "templates", "bundle.html")) else "index.html"
        return templates.TemplateResponse(template_name, {
            "request": request,
            "bundle": bundle,
            "user_id": user_id,
            "code": code
        })


@router.get("/api/bundle/{code}")
async def get_bundle_api(request: Request, code: str):
    """
    Fetch bundle metadata and files via JSON API.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not bundle:
            raise HTTPException(404, "Bundle not found")

        # Check bundle-level password lock
        if bundle.get("is_password_protected") and str(bundle["owner_id"]) != user_id:
            access = await db_bundles.get_or_create_bundle_access(conn, bundle["id"], uuid.UUID(user_id))
            if access.get("locked_until") and access["locked_until"] > datetime.utcnow():
                raise HTTPException(403, "Too many failed password attempts")
            if not access.get("first_success_at"):
                return JSONResponse(status_code=403, content={"ok": False, "requires_password": True, "bundle": {"id": str(bundle["id"]), "code": code, "title": bundle.get("title")}} )

        # Include both encoded_content and decompressed content for text files
        if bundle["bundle_type"] == "text" and bundle.get("files"):
            for f in bundle["files"]:
                full_f = await db_bundles.get_bundle_text_file(conn, f["id"])
                if full_f and full_f.get("encoded_content"):
                    f["encoded_content"] = full_f["encoded_content"]
                    try:
                        f["content"] = decompress_code(full_f["encoded_content"])
                    except Exception:
                        f["content"] = ""
                else:
                    f["encoded_content"] = ""
                    f["content"] = ""

        return {"ok": True, "bundle": bundle}


@router.post("/b/{code}/verify")
async def verify_bundle_password(request: Request, code: str, payload: VerifyPasswordRequest):
    """
    Verify bundle-level password.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not bundle or not bundle.get("is_password_protected"):
            raise HTTPException(404, "Bundle not found or not password protected")

        uid = uuid.UUID(user_id)
        access = await db_bundles.get_or_create_bundle_access(conn, bundle["id"], uid)
        if access.get("locked_until") and access["locked_until"] > datetime.utcnow():
            raise HTTPException(403, "Too many failed attempts. Try again later.")

        # Get parent bundle row with password_hash
        parent_row = await conn.fetchrow("SELECT password_hash FROM bundles WHERE id = $1", bundle["id"])
        if not parent_row or not verify_password(payload.password, parent_row["password_hash"] or ""):
            await db_bundles.increment_bundle_failed_attempt(conn, bundle["id"], uid)
            raise HTTPException(401, "Incorrect password")

        await db_bundles.mark_bundle_access_success(conn, bundle["id"], uid)
        return {"ok": True, "message": "Bundle unlocked"}


@router.post("/b/{code}/files/text")
async def add_text_file_endpoint(request: Request, code: str, payload: AddTextFileRequest):
    """
    Add a new text file to a text bundle (owner-only, max 5).
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not bundle:
            raise HTTPException(404, "Bundle not found")

        if str(bundle["owner_id"]) != user_id:
            raise HTTPException(403, "Owner-only operation")

        if bundle["bundle_type"] != "text":
            raise HTTPException(400, "Cannot add a text file to a binary bundle")

        content_str = payload.content or ""
        lang = payload.language or (detect_language(content_str) if content_str else "text")
        file_pwd_hash = hash_password(payload.password) if payload.password else None
        encoded = compress_code(content_str)

        try:
            new_file = await db_bundles.add_bundle_text_file(
                conn,
                bundle_id=bundle["id"],
                name=payload.name or "untitled",
                language=lang,
                password_hash=file_pwd_hash
            )
            await db_bundles.flush_bundle_text_file(conn, new_file["id"], encoded, uuid.UUID(user_id))
            new_file["content"] = content_str
            return {"ok": True, "file": new_file}
        except ValueError as e:
            raise HTTPException(400, str(e))


@router.post("/b/{code}/files/binary")
async def add_binary_file_endpoint(
    request: Request,
    code: str,
    name: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    """
    Add a new binary file to a binary bundle (owner-only, max 5).
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(400, "Empty file upload is not allowed")

    validation = validate_upload_file(file.filename or "", len(raw_bytes), file.content_type)
    if not validation["ok"]:
        raise HTTPException(400, validation["error"])

    async with get_conn() as conn:
        bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not bundle:
            raise HTTPException(404, "Bundle not found")

        if str(bundle["owner_id"]) != user_id:
            raise HTTPException(403, "Owner-only operation")

        if bundle["bundle_type"] != "binary":
            raise HTTPException(400, "Cannot add a binary file to a text bundle")

        if validation.get("is_text"):
            raise HTTPException(400, "Cannot add a text file to a binary bundle")

        r2_file_id = generate_id()
        save_uploaded_file(
            file_id=r2_file_id,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            content=raw_bytes,
        )

        file_pwd_hash = hash_password(password) if password else None
        try:
            new_file = await db_bundles.add_bundle_binary_file(
                conn,
                bundle_id=bundle["id"],
                file_id=r2_file_id,
                name=name or file.filename or "untitled",
                original_filename=file.filename or "upload",
                file_type=validation.get("extension") or "bin",
                file_size_bytes=len(raw_bytes),
                password_hash=file_pwd_hash,
            )
            return {"ok": True, "file": new_file}
        except ValueError as e:
            raise HTTPException(400, str(e))


@router.delete("/b/{code}")
async def delete_bundle_endpoint(request: Request, code: str):
    """
    Delete an entire bundle and its associated R2 files if binary (owner-only).
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        success, r2_keys = await db_bundles.delete_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not success:
            raise HTTPException(404, "Bundle not found or unauthorized")

    # Clean up R2 objects if binary bundle
    for r2_key in r2_keys:
        delete_uploaded_file(r2_key)

    return {"ok": True}


@router.delete("/b/{code}/files/{file_identifier}")
async def delete_file_endpoint(request: Request, code: str, file_identifier: str):
    """
    Remove a file tab from a bundle by file code or ID (owner-only, min 1 file remaining).
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not bundle:
            raise HTTPException(404, "Bundle not found")

        if str(bundle["owner_id"]) != user_id:
            raise HTTPException(403, "Owner-only operation")

        try:
            if bundle["bundle_type"] == "text":
                success = await db_bundles.delete_bundle_text_file(conn, bundle["id"], file_identifier)
                if not success:
                    raise HTTPException(404, "File not found")
            else:
                r2_file_id = await db_bundles.delete_bundle_binary_file(conn, bundle["id"], file_identifier)
                if not r2_file_id:
                    raise HTTPException(404, "File not found")
                delete_uploaded_file(r2_file_id)

            return {"ok": True}
        except ValueError as e:
            raise HTTPException(400, str(e))


@router.patch("/b/{code}/files/{file_identifier}")
async def rename_file_endpoint(request: Request, code: str, file_identifier: str, payload: RenameFileRequest):
    """
    Rename a file in a bundle by file code or ID (owner or anyone if permission == 'anyone').
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not bundle:
            raise HTTPException(404, "Bundle not found")

        if not bundle.get("can_edit"):
            raise HTTPException(403, "Permission denied")

        if bundle["bundle_type"] == "text":
            new_lang = payload.language or detect_language(payload.name)
            updated = await db_bundles.rename_bundle_text_file(conn, bundle["id"], file_identifier, payload.name, new_lang)
        else:
            updated = await db_bundles.rename_bundle_binary_file(conn, bundle["id"], file_identifier, payload.name)

        if not updated:
            raise HTTPException(404, "File not found")

        return {"ok": True, "file": updated}


@router.patch("/b/{code}/permission")
async def update_permission_endpoint(request: Request, code: str, payload: UpdatePermissionRequest):
    """
    Toggle bundle permission ('admin_only' ↔ 'anyone'). Owner-only.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    async with get_conn() as conn:
        updated_bundle = await db_bundles.update_bundle_permission(
            conn,
            code=code,
            owner_id=uuid.UUID(user_id),
            permission=payload.permission
        )
        if not updated_bundle:
            raise HTTPException(404, "Bundle not found or unauthorized")
        return {"ok": True, "permission": updated_bundle["permission"]}


@router.post("/b/{code}/files/{file_identifier}/flush")
async def flush_file_endpoint(request: Request, code: str, file_identifier: str):
    """
    Flush endpoint triggered by frontend idle detection (5s debounce).
    Reads latest raw text from Redis for the OT room, compresses it, and updates PG.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Login required")

    room_id = f"bundle_file:{file_identifier}"

    # Read current doc string from Redis room
    content, _ = await room_state.get_room_doc(room_id)
    encoded = compress_code(content or "")

    async with get_conn() as conn:
        bundle = await db_bundles.get_bundle_by_code(conn, code, uuid.UUID(user_id))
        if not bundle or bundle["bundle_type"] != "text":
            raise HTTPException(400, "Flush only applies to text bundle files")

        if not bundle.get("can_edit"):
            raise HTTPException(403, "Permission denied")

        success = await db_bundles.flush_bundle_text_file(
            conn,
            file_identifier=file_identifier,
            encoded_content=encoded,
            last_edited_by=uuid.UUID(user_id)
        )
        if not success:
            raise HTTPException(404, "File not found")

        return {"ok": True, "message": "File flushed to database"}
