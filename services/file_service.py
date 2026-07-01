from typing import Optional

from core.r2_client import get_r2_client

ALLOWED_TYPES = {
    "image": {"image/jpeg": 500 * 1024, "image/png": 500 * 1024, "image/svg+xml": 500 * 1024},
    "document": {"application/pdf": 500 * 1024, "application/vnd.openxmlformats-officedocument.wordprocessingml.document": 500 * 1024, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": 500 * 1024},
    "video": {"video/mp4": 5 * 1024 * 1024},
}

ALLOWED_EXTENSIONS = {
    "image": {"jpg", "jpeg", "png", "svg"},
    "document": {"pdf", "docx", "xlsx"},
    "video": {"mp4"},
}


def _extension_from_name(filename: str) -> str:
    if not filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def validate_upload_file(filename: str, size_bytes: int, mimetype: Optional[str] = None) -> dict:
    ext = _extension_from_name(filename)
    normalized_mimetype = (mimetype or "").split(";", 1)[0].strip().lower()

    if ext in {"zip", "rar", "7z"}:
        return {"ok": False, "error": "Unsupported file type. ZIP files are not supported."}

    category = None
    for candidate, rules in ALLOWED_TYPES.items():
        if normalized_mimetype in rules or ext in ALLOWED_EXTENSIONS[candidate]:
            category = candidate
            break

    if not category:
        return {"ok": False, "error": "Unsupported file type. Only image, document, and video files are supported."}

    max_bytes = None
    for rule_mimetype, rule_size in ALLOWED_TYPES[category].items():
        if normalized_mimetype in {rule_mimetype} or ext in ALLOWED_EXTENSIONS[category]:
            max_bytes = rule_size
            break

    if max_bytes is None:
        return {"ok": False, "error": "Unsupported file type. Only image, document, and video files are supported."}

    if size_bytes > max_bytes:
        return {"ok": False, "error": f"File is too large. Maximum allowed size is {max_bytes // 1024}KB."}

    return {"ok": True, "category": category, "extension": ext, "max_bytes": max_bytes}


def save_uploaded_file(file_id: str, filename: str, content_type: str, content: bytes, storage_dir: Optional[str] = None) -> dict:
    client, bucket_name = get_r2_client()
    client.put_object(
        Bucket=bucket_name,
        Key=file_id,
        Body=content,
        ContentType=content_type,
        Metadata={"filename": filename},
    )
    return {
        "file_id": file_id,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(content),
    }


def load_uploaded_file(file_id: str, storage_dir: Optional[str] = None) -> Optional[dict]:
    client, bucket_name = get_r2_client()
    try:
        response = client.get_object(Bucket=bucket_name, Key=file_id)
    except Exception:
        return None

    body = response.get("Body")
    content = body.read() if body is not None else b""
    metadata = response.get("Metadata", {}) or {}
    return {
        "file_id": file_id,
        "content": content,
        "filename": metadata.get("filename", file_id),
        "content_type": response.get("ContentType", "application/octet-stream"),
        "size_bytes": response.get("ContentLength", len(content)),
    }
