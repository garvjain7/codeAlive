from datetime import datetime, timedelta
from uuid import UUID


async def create_anonymous_file_upload(conn, file_id: str, original_filename: str, file_type: str, file_size_bytes: int) -> None:
    await conn.execute(
        """
        INSERT INTO anonymous_file_uploads (file_id, original_filename, file_type, file_size_bytes)
        VALUES ($1, $2, $3, $4)
        """,
        file_id,
        original_filename,
        file_type,
        file_size_bytes,
    )


async def create_user_file_upload(
    conn,
    file_id: str,
    owner_id,
    title: str,
    original_filename: str,
    file_type: str,
    file_size_bytes: int,
    password_hash: str | None,
    expires_at: datetime,
) -> None:
    await conn.execute(
        """
        INSERT INTO user_file_uploads (
            file_id,
            owner_id,
            title,
            original_filename,
            file_type,
            file_size_bytes,
            is_password_protected,
            password_hash,
            expires_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        file_id,
        UUID(str(owner_id)),
        title,
        original_filename,
        file_type,
        file_size_bytes,
        password_hash is not None,
        password_hash,
        expires_at,
    )


async def get_file_record(conn, file_id: str):
    row = await conn.fetchrow(
        """
        SELECT file_id, original_filename, file_type, file_size_bytes, created_at, NULL::text AS title,
               NULL::uuid AS owner_id, NULL::boolean AS is_password_protected,
               NULL::text AS password_hash, NULL::timestamp AS expires_at, 'anonymous' AS share_type,
               NULL::uuid AS record_id
        FROM anonymous_file_uploads
        WHERE file_id = $1
        UNION ALL
        SELECT file_id, original_filename, file_type, file_size_bytes, created_at, title,
               owner_id, is_password_protected, password_hash, expires_at, 'user' AS share_type,
               id AS record_id
        FROM user_file_uploads
        WHERE file_id = $1
        LIMIT 1
        """,
        file_id,
    )
    return dict(row) if row else None


async def increment_file_download_count(conn, file_id: str) -> None:
    await conn.execute(
        """
        UPDATE user_file_uploads
        SET download_count = COALESCE(download_count, 0) + 1
        WHERE file_id = $1
        """,
        file_id,
    )


async def get_access_control(conn, record_id, user_id: str):
    row = await conn.fetchrow(
        """
        SELECT failed_attempts, locked_until, first_success_at
        FROM file_access_control
        WHERE file_id = $1 AND user_id = $2
        """,
        record_id,
        user_id,
    )
    return dict(row) if row else None


async def record_failed_access_attempt(conn, record_id, user_id: str) -> None:
    existing = await get_access_control(conn, record_id, user_id)
    if existing:
        failed_attempts = (existing.get("failed_attempts") or 0) + 1
        locked_until = None
        if failed_attempts >= 3:
            locked_until = datetime.utcnow() + timedelta(minutes=5)
        await conn.execute(
            """
            UPDATE file_access_control
            SET failed_attempts = $3,
                last_failed_at = now(),
                locked_until = $4
            WHERE file_id = $1 AND user_id = $2
            """,
            record_id,
            user_id,
            failed_attempts,
            locked_until,
        )
    else:
        await conn.execute(
            """
            INSERT INTO file_access_control (file_id, user_id, failed_attempts, last_failed_at)
            VALUES ($1, $2, 1, now())
            """,
            record_id,
            user_id,
        )


async def clear_failed_access_attempts(conn, record_id, user_id: str) -> None:
    await conn.execute(
        """
        DELETE FROM file_access_control
        WHERE file_id = $1 AND user_id = $2
        """,
        record_id,
        user_id,
    )


async def mark_file_access_success(conn, record_id, user_id: str) -> None:
    await conn.execute(
        """
        UPDATE file_access_control
        SET failed_attempts = 0,
            locked_until = NULL,
            first_success_at = COALESCE(first_success_at, now())
        WHERE file_id = $1 AND user_id = $2
        """,
        record_id,
        user_id,
    )


async def get_user_file_uploads(conn, owner_id) -> list:
    """Return all files uploaded by owner_id, newest first."""
    rows = await conn.fetch(
        """
        SELECT file_id, title, original_filename, file_type, file_size_bytes,
               is_password_protected, expires_at, created_at,
               COALESCE(download_count, 0) AS download_count
        FROM user_file_uploads
        WHERE owner_id = $1
        ORDER BY created_at DESC
        """,
        UUID(str(owner_id)),
    )
    return [dict(r) for r in rows]


async def delete_user_file_upload(conn, file_id: str, owner_id) -> bool:
    """Delete a file record (and its access control rows) owned by owner_id.
    Returns True if a row was deleted, False if not found / not owned."""
    # Remove access-control rows first (FK may exist)
    await conn.execute(
        "DELETE FROM file_access_control WHERE file_id = (SELECT id FROM user_file_uploads WHERE file_id = $1)",
        file_id,
    )
    result = await conn.execute(
        "DELETE FROM user_file_uploads WHERE file_id = $1 AND owner_id = $2",
        file_id,
        UUID(str(owner_id)),
    )
    return result != "DELETE 0"


async def update_user_file_password(conn, file_id: str, owner_id, password_hash: str | None) -> bool:
    """Set or clear the password on a user-owned file."""
    result = await conn.execute(
        """
        UPDATE user_file_uploads
        SET is_password_protected = $3,
            password_hash = $4
        WHERE file_id = $1 AND owner_id = $2
        """,
        file_id,
        UUID(str(owner_id)),
        password_hash is not None,
        password_hash,
    )
    return result != "UPDATE 0"


async def update_user_file_expiry(conn, file_id: str, owner_id, expires_at: datetime) -> bool:
    """Update the expiry timestamp of a user-owned file."""
    result = await conn.execute(
        """
        UPDATE user_file_uploads
        SET expires_at = $3
        WHERE file_id = $1 AND owner_id = $2
        """,
        file_id,
        UUID(str(owner_id)),
        expires_at,
    )
    return result != "UPDATE 0"
