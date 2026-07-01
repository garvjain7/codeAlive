"""
ot_collab/password_utils.py
---------------------------
bcrypt helpers for room passwords.

Kept as a thin wrapper so the hashing algorithm stays consistent
with the rest of CodeAlive and is changed in one place if needed.

Why bcrypt and not argon2id here:
  Room passwords are verified once per user per room entry.
  After verification the result is cached in Redis for the room lifetime.
  bcrypt is already the project standard and is sufficient for this
  threat model — room passwords are short-lived, low-value secrets
  compared to user account passwords.

NOT used for user account passwords — those have their own auth path.
"""

from __future__ import annotations
import bcrypt


def hash_password(plaintext: str) -> str:
    """
    Hash a room password with bcrypt.
    Returns the hash as a UTF-8 string for storage in PostgreSQL.

    Work factor 12 — same as the rest of CodeAlive.
    Takes ~250ms on a modern server. Acceptable for a one-time
    operation at room creation or password change time.
    """
    hashed = bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    Returns True if correct, False otherwise.

    Called during the WS join flow password gate.
    After a successful verify, the result is cached in Redis
    (room_state/auth_cache.py) so subsequent reconnects skip this check.

    Safe to call with an empty or None hashed — returns False immediately
    rather than raising. Guards against rooms with no password
    accidentally reaching the verify path.
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False