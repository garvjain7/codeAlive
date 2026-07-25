import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from services.file_service import load_uploaded_file, save_uploaded_file, validate_upload_file
from core.utils import compress_code, generate_id, validate_code
from db.snippets import create_anonymous, create_user_snippet
from db.connection import get_conn
from db.file_uploads import (
    clear_failed_access_attempts,
    create_anonymous_file_upload,
    create_user_file_upload,
    get_access_control,
    get_file_record,
    increment_file_download_count,
    mark_file_access_success,
    record_failed_access_attempt,
)
from ot_collab.password_utils import hash_password, verify_password
from datetime import datetime, timedelta

import uuid
from db.users import get_user_by_id

router = APIRouter(prefix="/api/files", tags=["files"])
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

_RESERVED = frozenset({"editor", "waitlist", "static", "s", "f", "new", "robots.txt", "sitemap.xml", "api", "import", "workspace", "profile", "login", "signup"})


async def resolve_file_id(conn, custom_code: str | None) -> str:
    if custom_code:
        custom_code = custom_code.strip()
        if not custom_code:
            raise HTTPException(400, "Custom code cannot be empty")
        if len(custom_code) > 30:
            raise HTTPException(400, "Custom code too long (max 30 chars)")
        if custom_code.lower() in _RESERVED:
            raise HTTPException(400, "That slug is reserved — pick another")
        existing = await get_file_record(conn, custom_code)
        if existing:
            raise HTTPException(400, "Custom code already taken")
        return custom_code

    while True:
        file_id = generate_id()
        existing = await get_file_record(conn, file_id)
        if not existing:
            return file_id


async def build_file_view_response(request: Request, file_id: str):
    stored_file = load_uploaded_file(file_id)
    if not stored_file:
        raise HTTPException(404, "File not found")

    user_id = getattr(request.state, "user_id", None)
    user_email = None

    async with get_conn() as conn:
        record = await get_file_record(conn, file_id)
        if record and record.get("share_type") == "user":
            if not user_id:
                return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)

            if record.get("expires_at") and record["expires_at"] < datetime.utcnow():
                raise HTTPException(404, "File has expired")

            access = await get_access_control(conn, record.get("record_id"), user_id)
            if access and access.get("locked_until") and access["locked_until"] > datetime.utcnow():
                raise HTTPException(403, "Too many failed attempts")

        if user_id:
            user = await get_user_by_id(conn, uuid.UUID(user_id))
            if user:
                user_email = user["email"]

    preview_text = None
    if stored_file["content_type"].startswith("text/") or stored_file["content_type"] in {
        "application/json",
        "application/xml",
        "application/javascript",
        "text/plain",
    }:
        try:
            preview_text = stored_file["content"].decode("utf-8")
        except UnicodeDecodeError:
            preview_text = stored_file["content"].decode("utf-8", errors="replace")

    return templates.TemplateResponse(
        "import.html",
        {
            "request": request,
            "file_id": file_id,
            "filename": stored_file["filename"],
            "content_type": stored_file["content_type"],
            "size_bytes": stored_file["size_bytes"],
            "download_url": f"/api/files/{file_id}",
            "share_url": f"/f/{file_id}",
            "user_id": user_id,
            "user_email": user_email,
            "is_password_protected": bool(record and record.get("is_password_protected")),
            "preview_text": preview_text,
            "preview_mode": "share",
            "preview_url": f"/api/files/{file_id}",
            "preview_content_type": stored_file["content_type"],
        },
    )


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(None),
    password: str = Form(None),
    expires_in_days: int = Form(30),
    custom_code: str = Form(None),
):
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(400, "Empty file upload is not allowed")

    validation = validate_upload_file(file.filename or "", len(raw_bytes), file.content_type)
    if not validation["ok"]:
        raise HTTPException(400, validation["error"])

    user_id = getattr(request.state, "user_id", None)
    if validation.get("is_text"):
        text = raw_bytes.decode("utf-8", errors="strict")
        validate_code(text)

        async with get_conn() as conn:
            code_id = generate_id()
            if user_id:
                if not title:
                    title = file.filename or "Imported Text"
                expires_at = datetime.utcnow() + timedelta(days=expires_in_days or 30)
                await create_user_snippet(
                    conn,
                    code_id=code_id,
                    owner_id=user_id,
                    encoded_content=compress_code(text),
                    language="text",
                    highlights="",
                    password_hash=hash_password(password) if password else None,
                    expires_at=expires_at,
                    title=title.strip(),
                )
            else:
                await create_anonymous(
                    conn,
                    code_id=code_id,
                    encoded_content=compress_code(text),
                    language="text",
                    highlights="",
                )

        return JSONResponse({
            "ok": True,
            "code_id": code_id,
            "url": f"/s/{code_id}",
            "message": "Text file imported into the editor flow.",
        })

    if user_id and not title:
        title = file.filename or "Imported File"

    async with get_conn() as conn:
        file_id = await resolve_file_id(conn, custom_code)

        saved_file = save_uploaded_file(
            file_id=file_id,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            content=raw_bytes,
        )

        if user_id:
            password_hash = hash_password(password) if password else None
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days or 30)
            await create_user_file_upload(
                conn,
                file_id=file_id,
                owner_id=user_id,
                title=title.strip(),
                original_filename=file.filename or "upload",
                file_type=validation["extension"],
                file_size_bytes=len(raw_bytes),
                password_hash=password_hash,
                expires_at=expires_at,
            )
        else:
            await create_anonymous_file_upload(
                conn,
                file_id=file_id,
                original_filename=file.filename or "upload",
                file_type=validation["extension"],
                file_size_bytes=len(raw_bytes),
            )

    return JSONResponse({
        "ok": True,
        "file_id": saved_file["file_id"],
        "filename": saved_file["filename"],
        "content_type": saved_file["content_type"],
        "size_bytes": saved_file["size_bytes"],
        "url": f"/f/{saved_file['file_id']}",
        "message": "Upload stored successfully.",
    })


@router.get("/{file_id}")
async def get_file(request: Request, file_id: str):
    stored_file = load_uploaded_file(file_id)
    if not stored_file:
        raise HTTPException(404, "File not found")

    async with get_conn() as conn:
        record = await get_file_record(conn, file_id)
        if record and record.get("share_type") == "user":
            user_id = getattr(request.state, "user_id", None)
            if not user_id:
                raise HTTPException(401, "Authentication required to access this file")
            if record.get("expires_at") and record["expires_at"] < datetime.utcnow():
                raise HTTPException(404, "File has expired")
            if record.get("is_password_protected"):
                access = await get_access_control(conn, record.get("record_id"), user_id)
                if access and access.get("locked_until") and access["locked_until"] > datetime.utcnow():
                    raise HTTPException(403, "Too many failed attempts")
                if not access or not access.get("first_success_at"):
                    raise HTTPException(403, "Password required")
            await increment_file_download_count(conn, file_id)

    disposition = "attachment" if file_id.endswith("download") else "inline"
    return Response(
        content=stored_file["content"],
        media_type=stored_file["content_type"],
        headers={"Content-Disposition": f"{disposition}; filename={stored_file['filename']}"},
    )


@router.get("/view/{file_id}", response_class=HTMLResponse)
async def view_file(request: Request, file_id: str):
    stored_file = load_uploaded_file(file_id)
    if not stored_file:
        raise HTTPException(404, "File not found")

    async with get_conn() as conn:
        record = await get_file_record(conn, file_id)
        if record and record.get("share_type") == "user":
            if record.get("expires_at") and record["expires_at"] < datetime.utcnow():
                raise HTTPException(404, "File has expired")
            user_id = getattr(request.state, "user_id", None)
            if record.get("is_password_protected") and not user_id:
                raise HTTPException(403, "Password protected")
            if record.get("is_password_protected") and user_id:
                access = await get_access_control(conn, record.get("record_id"), user_id)
                if access and access.get("locked_until") and access["locked_until"] > datetime.utcnow():
                    raise HTTPException(403, "Too many failed attempts")

    preview_text = None
    if stored_file["content_type"].startswith("text/") or stored_file["content_type"] in {
        "application/json",
        "application/xml",
        "application/javascript",
        "text/plain",
    }:
        try:
            preview_text = stored_file["content"].decode("utf-8")
        except UnicodeDecodeError:
            preview_text = stored_file["content"].decode("utf-8", errors="replace")

    return templates.TemplateResponse(
        "import.html",
        {
            "request": request,
            "file_id": file_id,
            "filename": stored_file["filename"],
            "content_type": stored_file["content_type"],
            "size_bytes": stored_file["size_bytes"],
            "download_url": f"/api/files/{file_id}",
            "share_url": f"/f/{file_id}",
            "user_id": getattr(request.state, "user_id", None),
            "is_password_protected": bool(record and record.get("is_password_protected")),
            "preview_text": preview_text,
            "preview_mode": "share",
            "preview_url": f"/api/files/{file_id}",
            "preview_content_type": stored_file["content_type"],
        },
    )


@router.post("/view/{file_id}/unlock")
async def unlock_file(request: Request, file_id: str, password: str = Form(...)):
    async with get_conn() as conn:
        record = await get_file_record(conn, file_id)
        if not record or record.get("share_type") != "user" or not record.get("is_password_protected"):
            raise HTTPException(404, "File not found")
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(403, "Authentication required")
        access = await get_access_control(conn, record.get("record_id"), user_id)
        if access and access.get("locked_until") and access["locked_until"] > datetime.utcnow():
            raise HTTPException(403, "Too many failed attempts")
        is_valid = verify_password(password, record.get("password_hash") or "")
        if not is_valid:
            await record_failed_access_attempt(conn, record.get("record_id"), user_id)
            raise HTTPException(403, "Incorrect password")
        await clear_failed_access_attempts(conn, record.get("record_id"), user_id)
        await mark_file_access_success(conn, record.get("record_id"), user_id)
        return JSONResponse({"ok": True, "message": "Unlocked"})
