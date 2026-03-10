import gzip
import base64
import secrets
import string
from fastapi import HTTPException

MAX_LINES = 1000
ID_LENGTH = 6
ID_ALPHABET = string.ascii_letters + string.digits


def validate_code(code: str):
    lines = code.splitlines()
    if len(lines) > MAX_LINES:
        raise HTTPException(status_code=400, detail="Code exceeds 1000 lines")


def compress_code(code: str) -> str:
    """Compress with gzip then encode as URL-safe Base64."""
    compressed = gzip.compress(code.encode())
    return base64.urlsafe_b64encode(compressed).decode()


def decompress_code(data: str) -> str:
    """Decode URL-safe Base64 then decompress gzip."""
    compressed = base64.urlsafe_b64decode(data)
    return gzip.decompress(compressed).decode()


def generate_id() -> str:
    """Generate a short random alphanumeric ID e.g. 5vdYxn."""
    return ''.join(secrets.choice(ID_ALPHABET) for _ in range(ID_LENGTH))