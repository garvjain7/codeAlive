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


def mask_email(email: str) -> str:
    """Mask email address using manual regex: contact@example.com -> c***@example.com"""
    if not email or "@" not in email:
        return "hidden"
    import re
    # Match the first char, then everything until @, then the domain
    return re.sub(r"(^.)[^@]+(@.+)", r"\1***\2", email)


def mask_text(text: str) -> str:
    """Mask sensitive identifiers: garvjain -> g***n"""
    if not text or len(text) < 2:
        return "***"
    import re
    # Keep first and last char, mask the middle
    return re.sub(r"(^.).+(.$)", r"\1***\2", text)


def safe_log(msg: str, data: dict = None):
    """Log a message while masking potential PII in the data dictionary."""
    if data:
        masked_data = {}
        for k, v in data.items():
            val = str(v)
            if any(pii in k.lower() for pii in ["email", "user", "identifier"]):
                masked_data[k] = mask_email(val) if "@" in val else mask_text(val)
            else:
                masked_data[k] = v
        print(f"[INFO] {msg} | Data: {masked_data}")
    else:
        print(f"[INFO] {msg}")