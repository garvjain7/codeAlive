import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from services.file_service import load_uploaded_file, save_uploaded_file, validate_upload_file
from core.utils import generate_id
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

router = APIRouter(prefix="/api/files", tags=["files"])
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))


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
    if user_id and not title:
        raise HTTPException(400, "Title is mandatory for logged-in file uploads")

    file_id = generate_id()
    saved_file = save_uploaded_file(
        file_id=file_id,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        content=raw_bytes,
    )

    async with get_conn() as conn:
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
            if record.get("expires_at") and record["expires_at"] < datetime.utcnow():
                raise HTTPException(404, "File has expired")
            user_id = getattr(request.state, "user_id", None)
            if record.get("is_password_protected") and not user_id:
                raise HTTPException(403, "Password protected")
            if record.get("is_password_protected") and user_id:
                access = await get_access_control(conn, file_id, user_id)
                if access and access.get("locked_until") and access["locked_until"] > datetime.utcnow():
                    raise HTTPException(403, "Too many failed attempts")
                if not access or not access.get("first_success_at"):
                    raise HTTPException(403, "Password required")
            if record.get("share_type") == "user":
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
                access = await get_access_control(conn, file_id, user_id)
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
        "file_viewer.html",
        {
            "request": request,
            "file_id": file_id,
            "filename": stored_file["filename"],
            "content_type": stored_file["content_type"],
            "size_bytes": stored_file["size_bytes"],
            "download_url": f"/api/files/{file_id}",
            "is_password_protected": bool(record and record.get("is_password_protected")),
            "preview_text": preview_text,
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
        access = await get_access_control(conn, file_id, user_id)
        if access and access.get("locked_until") and access["locked_until"] > datetime.utcnow():
            raise HTTPException(403, "Too many failed attempts")
        is_valid = verify_password(password, record.get("password_hash") or "")
        if not is_valid:
            await record_failed_access_attempt(conn, record.get("record_id"), user_id)
            raise HTTPException(403, "Incorrect password")
        await mark_file_access_success(conn, record.get("record_id"), user_id)
        return JSONResponse({"ok": True, "message": "Unlocked"})
