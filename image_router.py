import base64

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response

from image_service import save_image, get_image

router = APIRouter()

# ── POST /upload-image ────────────────────────────────────────────────────────

@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """
    Accept an image upload, compress it, store it in MongoDB.

    Returns: { image_id }

    Error responses:
      415 — not an image file
      413 — file exceeds 1MB
      422 — cannot compress below 200KB
      500 — unexpected server error
    """
    # Read raw bytes
    raw_bytes = await file.read()
    mimetype  = file.content_type or ""

    try:
        result = save_image(raw_bytes, mimetype)
    except ValueError as e:
        msg = str(e)
        # Map error message to appropriate HTTP status
        if "too large" in msg:
            raise HTTPException(status_code=413, detail=msg)
        elif "Invalid file type" in msg:
            raise HTTPException(status_code=415, detail=msg)
        elif "cannot be compressed" in msg:
            raise HTTPException(status_code=422, detail=msg)
        else:
            raise HTTPException(status_code=422, detail=msg)

    return {"image_id": result["image_id"]}


# ── GET /image/{image_id} ─────────────────────────────────────────────────────

@router.get("/image/{image_id}")
async def serve_image(image_id: str):
    """
    Serve a stored image as JPEG binary.
    The frontend opens this URL in a new tab using window.open().
    """
    # Basic ID validation — only allow safe characters
    if not image_id.startswith("img_") or len(image_id) > 30:
        raise HTTPException(status_code=404, detail="Image not found")

    doc = get_image(image_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Image not found")

    image_bytes = base64.b64decode(doc["data"])

    return Response(
        content=image_bytes,
        media_type="image/jpeg",
        headers={
            # Allow browser to cache the image for 7 days
            "Cache-Control": "public, max-age=604800",
        },
    )