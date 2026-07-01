import io
import base64
from datetime import datetime, timezone

from PIL import Image
import uuid

from core.mongodb import images_collection

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_UPLOAD_BYTES     = 1 * 1024 * 1024   # 1 MB   — reject before compression
MAX_COMPRESSED_BYTES = 200 * 1024        # 200 KB  — reject after compression
STORAGE_LIMIT_BYTES  = 512 * 1024 * 1024 # 512 MB  — total MongoDB image budget
MAX_DIMENSION        = 1200              # px — resize if wider/taller than this

ALLOWED_MIMETYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}

# ── ID generation ──────────────────────────────────────────────────────────────

def generate_image_id() -> str:
    return f"img_{uuid.uuid4().hex[:10]}"

# ── Compression ───────────────────────────────────────────────────────────────

def compress_image(data: bytes, mimetype: str) -> bytes:
    """
    Compress an image using Pillow + JPEG encoding.

    Strategy:
      1. Open image, convert to RGB (handles PNG/WEBP alpha channels)
      2. Resize if either dimension exceeds MAX_DIMENSION (aspect ratio preserved)
      3. Try JPEG quality=75 first
      4. If still > 200KB, try quality=50
      5. If still > 200KB, raise ValueError — caller rejects the upload

    Returns compressed JPEG bytes.
    """
    img = Image.open(io.BytesIO(data)).convert("RGB")

    # ── Resize if needed ──────────────────────────────────────────────────────
    w, h = img.size
    if w > MAX_DIMENSION or h > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    # ── Try quality=75 ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    compressed = buf.getvalue()

    if len(compressed) <= MAX_COMPRESSED_BYTES:
        return compressed

    # ── Try quality=50 ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=50, optimize=True)
    compressed = buf.getvalue()

    if len(compressed) <= MAX_COMPRESSED_BYTES:
        return compressed

    raise ValueError(
        f"Image cannot be compressed below 200KB "
        f"(smallest attempt: {len(compressed) // 1024}KB). "
        f"Please use a smaller image."
    )

# ── FIFO eviction ─────────────────────────────────────────────────────────────

def evict_if_needed(incoming_size: int) -> None:
    """
    Check total stored image size. If adding incoming_size would exceed
    STORAGE_LIMIT_BYTES, delete oldest images (by created_at) until there
    is enough room.

    Called synchronously at write time — no background worker needed.
    """
    # Sum compressed_size across all documents
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$compressed_size"}}}]
    result   = list(images_collection.aggregate(pipeline))
    total    = result[0]["total"] if result else 0

    if total + incoming_size <= STORAGE_LIMIT_BYTES:
        return  # Enough space — nothing to do

    # Delete oldest first until we have room
    needed   = (total + incoming_size) - STORAGE_LIMIT_BYTES
    freed    = 0
    oldest   = images_collection.find(
        {}, {"_id": 1, "compressed_size": 1}
    ).sort("created_at", 1)  # ascending = oldest first

    ids_to_delete = []
    for doc in oldest:
        ids_to_delete.append(doc["_id"])
        freed += doc.get("compressed_size", 0)
        if freed >= needed:
            break

    if ids_to_delete:
        images_collection.delete_many({"_id": {"$in": ids_to_delete}})
        print(f"🗑️  FIFO eviction: deleted {len(ids_to_delete)} images, freed ~{freed // 1024}KB")

# ── Save image ────────────────────────────────────────────────────────────────

def save_image(raw_bytes: bytes, mimetype: str) -> dict:
    """
    Full pipeline: validate → compress → evict if needed → save to MongoDB.

    Returns: { image_id, compressed_size, original_size }
    Raises:  ValueError for validation/compression failures
    """
    # ── Validate upload size ──────────────────────────────────────────────────
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"File too large ({len(raw_bytes) // 1024}KB). Maximum upload size is 1MB."
        )

    # ── Validate mimetype ─────────────────────────────────────────────────────
    if mimetype not in ALLOWED_MIMETYPES:
        raise ValueError(
            f"Invalid file type '{mimetype}'. Only JPEG, PNG, GIF and WebP are allowed."
        )

    # ── Compress ──────────────────────────────────────────────────────────────
    compressed = compress_image(raw_bytes, mimetype)

    # ── Evict oldest images if storage is full ────────────────────────────────
    evict_if_needed(len(compressed))

    # ── Build document ────────────────────────────────────────────────────────
    image_id = generate_image_id()
    document = {
        "_id":             image_id,
        "data":            base64.b64encode(compressed).decode("utf-8"),
        "mimetype":        "image/jpeg",   # always JPEG after compression
        "original_size":   len(raw_bytes),
        "compressed_size": len(compressed),
        "created_at":      datetime.now(timezone.utc),
    }

    images_collection.insert_one(document)

    print(
        f"✅ Image saved: {image_id} | "
        f"original={len(raw_bytes) // 1024}KB | "
        f"compressed={len(compressed) // 1024}KB"
    )

    return {
        "image_id":        image_id,
        "original_size":   len(raw_bytes),
        "compressed_size": len(compressed),
    }

# ── Fetch image ───────────────────────────────────────────────────────────────

def get_image(image_id: str) -> dict | None:
    """
    Fetch an image document by ID.
    Returns the full document or None if not found.
    """
    return images_collection.find_one({"_id": image_id})