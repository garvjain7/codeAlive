from typing import Optional, Tuple, List
from uuid import UUID
from core.utils import generate_id


# ─────────────────────────────────────────────────────────────────────────────
# BUNDLE CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def create_bundle(
    conn,
    owner_id,
    code: str,
    bundle_type: str,
    title: Optional[str] = None,
    permission: str = "admin_only",
    expires_at=None,
    password_hash: Optional[str] = None,
) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO bundles (owner_id, code, title, bundle_type, permission,
                             expires_at, is_password_protected, password_hash)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, code, owner_id, title, bundle_type, permission,
                  expires_at, is_password_protected, created_at, updated_at
        """,
        UUID(str(owner_id)),
        code,
        title,
        bundle_type,
        permission,
        expires_at,
        password_hash is not None,
        password_hash,
    )
    return dict(row)


async def get_bundle_by_code(conn, code: str, requester_id) -> Optional[dict]:
    bundle = await conn.fetchrow(
        """
        SELECT id, code, owner_id, title, bundle_type, permission,
               expires_at, is_password_protected, created_at, updated_at
        FROM bundles
        WHERE code = $1
        """,
        code,
    )
    if not bundle:
        return None

    bundle_dict = dict(bundle)
    requester_uuid = UUID(str(requester_id))
    bundle_dict["can_edit"] = (
        bundle_dict["owner_id"] == requester_uuid
        or bundle_dict["permission"] == "anyone"
    )

    if bundle_dict["bundle_type"] == "text":
        file_rows = await conn.fetch(
            """
            SELECT id, code, name, language, position, is_password_protected, last_edited_by,
                   created_at, updated_at
            FROM bundle_text_files
            WHERE bundle_id = $1
            ORDER BY position ASC
            """,
            bundle_dict["id"],
        )
    else:
        file_rows = await conn.fetch(
            """
            SELECT id, file_id, code, name, original_filename, file_type, file_size_bytes,
                   position, is_password_protected, download_count, created_at, updated_at
            FROM bundle_binary_files
            WHERE bundle_id = $1
            ORDER BY position ASC
            """,
            bundle_dict["id"],
        )

    bundle_dict["files"] = [dict(r) for r in file_rows]
    return bundle_dict


async def get_user_bundles(conn, owner_id) -> list:
    rows = await conn.fetch(
        """
        SELECT b.id, b.code, b.title, b.bundle_type, b.permission, b.expires_at,
               b.is_password_protected, b.created_at, b.updated_at,
               CASE 
                   WHEN b.bundle_type = 'text' THEN (SELECT COUNT(*) FROM bundle_text_files WHERE bundle_id = b.id)
                   ELSE (SELECT COUNT(*) FROM bundle_binary_files WHERE bundle_id = b.id)
               END AS file_count
        FROM bundles b
        WHERE b.owner_id = $1
        ORDER BY b.created_at DESC
        """,
        UUID(str(owner_id)),
    )
    return [dict(r) for r in rows]


async def update_bundle_permission(conn, code: str, owner_id, permission: str) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        UPDATE bundles
        SET permission = $3, updated_at = now()
        WHERE code = $1 AND owner_id = $2
        RETURNING id, code, owner_id, permission, updated_at
        """,
        code,
        UUID(str(owner_id)),
        permission,
    )
    return dict(row) if row else None


async def delete_bundle_by_code(conn, code: str, owner_id) -> Tuple[bool, List[str]]:
    """
    Deletes a user-owned bundle by code.
    If binary bundle, collects and returns R2 object keys to delete from cloud storage.
    Returns (success_boolean, list_of_r2_keys).
    """
    owner_uuid = UUID(str(owner_id))

    async with conn.transaction():
        bundle = await conn.fetchrow(
            "SELECT id, bundle_type FROM bundles WHERE code = $1 AND owner_id = $2 FOR UPDATE",
            code,
            owner_uuid,
        )
        if not bundle:
            return False, []

        r2_keys = []
        if bundle["bundle_type"] == "binary":
            rows = await conn.fetch(
                "SELECT file_id FROM bundle_binary_files WHERE bundle_id = $1",
                bundle["id"],
            )
            r2_keys = [r["file_id"] for r in rows]

        await conn.execute("DELETE FROM bundles WHERE id = $1", bundle["id"])

    return True, r2_keys


# ─────────────────────────────────────────────────────────────────────────────
# TEXT FILE CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def add_bundle_text_file(
    conn,
    bundle_id,
    name: str,
    language: Optional[str] = None,
    password_hash: Optional[str] = None,
    file_code: Optional[str] = None,
) -> dict:
    bundle_uuid = UUID(str(bundle_id))
    code_str = file_code.strip() if file_code else generate_id()

    async with conn.transaction():
        await conn.fetchrow(
            "SELECT id FROM bundles WHERE id = $1 FOR UPDATE",
            bundle_uuid,
        )

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM bundle_text_files WHERE bundle_id = $1",
            bundle_uuid,
        )
        if count >= 5:
            raise ValueError("Bundle already has 5 files")

        position = count + 1
        row = await conn.fetchrow(
            """
            INSERT INTO bundle_text_files
                (bundle_id, code, name, encoded_content, language, position,
                 is_password_protected, password_hash)
            VALUES ($1, $2, $3, '', $4, $5, $6, $7)
            RETURNING id, bundle_id, code, name, language, position,
                      is_password_protected, created_at, updated_at
            """,
            bundle_uuid,
            code_str,
            name,
            language,
            position,
            password_hash is not None,
            password_hash,
        )

    return dict(row)


async def get_bundle_text_file(conn, file_identifier) -> Optional[dict]:
    """Returns the full row including encoded_content — accepts UUID or code string."""
    try:
        file_uuid = UUID(str(file_identifier))
        row = await conn.fetchrow(
            """
            SELECT id, bundle_id, code, name, encoded_content, language, position,
                   is_password_protected, password_hash, last_edited_by, updated_at
            FROM bundle_text_files
            WHERE id = $1
            """,
            file_uuid,
        )
    except ValueError:
        row = await conn.fetchrow(
            """
            SELECT id, bundle_id, code, name, encoded_content, language, position,
                   is_password_protected, password_hash, last_edited_by, updated_at
            FROM bundle_text_files
            WHERE code = $1
            """,
            str(file_identifier),
        )
    return dict(row) if row else None


async def flush_bundle_text_file(
    conn,
    file_identifier,
    encoded_content: str,
    last_edited_by,
) -> bool:
    """Write compressed content from OT layer to PG. Accepts file UUID or code."""
    try:
        file_uuid = UUID(str(file_identifier))
        result = await conn.execute(
            """
            UPDATE bundle_text_files
            SET encoded_content = $2,
                last_edited_by = $3,
                updated_at = now()
            WHERE id = $1
            """,
            file_uuid,
            encoded_content,
            UUID(str(last_edited_by)) if last_edited_by else None,
        )
    except ValueError:
        result = await conn.execute(
            """
            UPDATE bundle_text_files
            SET encoded_content = $2,
                last_edited_by = $3,
                updated_at = now()
            WHERE code = $1
            """,
            str(file_identifier),
            encoded_content,
            UUID(str(last_edited_by)) if last_edited_by else None,
        )
    return result != "UPDATE 0"


async def rename_bundle_text_file(
    conn,
    bundle_id,
    file_identifier,
    new_name: str,
    new_language: Optional[str],
) -> Optional[dict]:
    bundle_uuid = UUID(str(bundle_id))
    try:
        file_uuid = UUID(str(file_identifier))
        row = await conn.fetchrow(
            """
            UPDATE bundle_text_files
            SET name = $3, language = $4, updated_at = now()
            WHERE id = $2 AND bundle_id = $1
            RETURNING id, bundle_id, code, name, language, position, updated_at
            """,
            bundle_uuid,
            file_uuid,
            new_name,
            new_language,
        )
    except ValueError:
        row = await conn.fetchrow(
            """
            UPDATE bundle_text_files
            SET name = $3, language = $4, updated_at = now()
            WHERE code = $2 AND bundle_id = $1
            RETURNING id, bundle_id, code, name, language, position, updated_at
            """,
            bundle_uuid,
            str(file_identifier),
            new_name,
            new_language,
        )
    return dict(row) if row else None


async def delete_bundle_text_file(conn, bundle_id, file_identifier) -> bool:
    bundle_uuid = UUID(str(bundle_id))

    async with conn.transaction():
        await conn.fetchrow(
            "SELECT id FROM bundles WHERE id = $1 FOR UPDATE",
            bundle_uuid,
        )

        file_count = await conn.fetchval(
            "SELECT COUNT(*) FROM bundle_text_files WHERE bundle_id = $1",
            bundle_uuid,
        )
        if file_count <= 1:
            raise ValueError("Cannot delete the last file in a bundle")

        try:
            file_uuid = UUID(str(file_identifier))
            deleted = await conn.fetchrow(
                "DELETE FROM bundle_text_files WHERE id = $1 AND bundle_id = $2 RETURNING position",
                file_uuid,
                bundle_uuid,
            )
        except ValueError:
            deleted = await conn.fetchrow(
                "DELETE FROM bundle_text_files WHERE code = $1 AND bundle_id = $2 RETURNING position",
                str(file_identifier),
                bundle_uuid,
            )

        if not deleted:
            return False

        deleted_position = deleted["position"]

        await conn.execute(
            """
            UPDATE bundle_text_files
            SET position = position - 1
            WHERE bundle_id = $1 AND position > $2
            """,
            bundle_uuid,
            deleted_position,
        )

    return True


# ─────────────────────────────────────────────────────────────────────────────
# BINARY FILE CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def add_bundle_binary_file(
    conn,
    bundle_id,
    file_id: str,
    name: str,
    original_filename: str,
    file_type: str,
    file_size_bytes: int,
    password_hash: Optional[str] = None,
    file_code: Optional[str] = None,
) -> dict:
    bundle_uuid = UUID(str(bundle_id))
    code_str = file_code.strip() if file_code else generate_id()

    async with conn.transaction():
        await conn.fetchrow(
            "SELECT id FROM bundles WHERE id = $1 FOR UPDATE",
            bundle_uuid,
        )

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM bundle_binary_files WHERE bundle_id = $1",
            bundle_uuid,
        )
        if count >= 5:
            raise ValueError("Bundle already has 5 files")

        position = count + 1
        row = await conn.fetchrow(
            """
            INSERT INTO bundle_binary_files
                (file_id, bundle_id, code, name, original_filename, file_type, file_size_bytes,
                 position, is_password_protected, password_hash)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id, file_id, bundle_id, code, name, original_filename, file_type,
                      file_size_bytes, position, is_password_protected,
                      download_count, created_at, updated_at
            """,
            file_id,
            bundle_uuid,
            code_str,
            name,
            original_filename,
            file_type,
            file_size_bytes,
            position,
            password_hash is not None,
            password_hash,
        )

    return dict(row)


async def rename_bundle_binary_file(
    conn,
    bundle_id,
    file_identifier,
    new_name: str,
) -> Optional[dict]:
    bundle_uuid = UUID(str(bundle_id))
    try:
        file_uuid = UUID(str(file_identifier))
        row = await conn.fetchrow(
            """
            UPDATE bundle_binary_files
            SET name = $3, updated_at = now()
            WHERE id = $2 AND bundle_id = $1
            RETURNING id, file_id, bundle_id, code, name, position, updated_at
            """,
            bundle_uuid,
            file_uuid,
            new_name,
        )
    except ValueError:
        row = await conn.fetchrow(
            """
            UPDATE bundle_binary_files
            SET name = $3, updated_at = now()
            WHERE code = $2 AND bundle_id = $1
            RETURNING id, file_id, bundle_id, code, name, position, updated_at
            """,
            bundle_uuid,
            str(file_identifier),
            new_name,
        )
    return dict(row) if row else None


async def delete_bundle_binary_file(conn, bundle_id, file_identifier) -> Optional[str]:
    """Returns the R2 file_id (object key) so the router can delete from R2. Returns None if not found."""
    bundle_uuid = UUID(str(bundle_id))

    async with conn.transaction():
        await conn.fetchrow(
            "SELECT id FROM bundles WHERE id = $1 FOR UPDATE",
            bundle_uuid,
        )

        file_count = await conn.fetchval(
            "SELECT COUNT(*) FROM bundle_binary_files WHERE bundle_id = $1",
            bundle_uuid,
        )
        if file_count <= 1:
            raise ValueError("Cannot delete the last file in a bundle")

        try:
            file_uuid = UUID(str(file_identifier))
            deleted = await conn.fetchrow(
                """
                DELETE FROM bundle_binary_files
                WHERE id = $1 AND bundle_id = $2
                RETURNING file_id, position
                """,
                file_uuid,
                bundle_uuid,
            )
        except ValueError:
            deleted = await conn.fetchrow(
                """
                DELETE FROM bundle_binary_files
                WHERE code = $1 AND bundle_id = $2
                RETURNING file_id, position
                """,
                str(file_identifier),
                bundle_uuid,
            )

        if not deleted:
            return None

        deleted_position = deleted["position"]

        await conn.execute(
            """
            UPDATE bundle_binary_files
            SET position = position - 1
            WHERE bundle_id = $1 AND position > $2
            """,
            bundle_uuid,
            deleted_position,
        )

    return deleted["file_id"]


async def increment_binary_file_download(conn, file_identifier) -> None:
    try:
        file_uuid = UUID(str(file_identifier))
        await conn.execute(
            "UPDATE bundle_binary_files SET download_count = download_count + 1 WHERE id = $1",
            file_uuid,
        )
    except ValueError:
        await conn.execute(
            "UPDATE bundle_binary_files SET download_count = download_count + 1 WHERE code = $1",
            str(file_identifier),
        )


# ─────────────────────────────────────────────────────────────────────────────
# BUNDLE-LEVEL ACCESS CONTROL
# ─────────────────────────────────────────────────────────────────────────────

async def get_or_create_bundle_access(conn, bundle_id, user_id) -> dict:
    row = await conn.fetchrow(
        """
        SELECT failed_attempts, locked_until, first_success_at
        FROM bundle_access_control
        WHERE bundle_id = $1 AND user_id = $2
        """,
        UUID(str(bundle_id)),
        UUID(str(user_id)),
    )
    if not row:
        await conn.execute(
            "INSERT INTO bundle_access_control (bundle_id, user_id) VALUES ($1, $2)",
            UUID(str(bundle_id)),
            UUID(str(user_id)),
        )
        return {"failed_attempts": 0, "locked_until": None, "first_success_at": None}
    return dict(row)


async def increment_bundle_failed_attempt(conn, bundle_id, user_id) -> None:
    await conn.execute(
        """
        UPDATE bundle_access_control
        SET failed_attempts = failed_attempts + 1,
            last_failed_at = now(),
            locked_until = CASE
                WHEN failed_attempts + 1 >= 3 THEN now() + INTERVAL '10 minutes'
                ELSE locked_until
            END
        WHERE bundle_id = $1 AND user_id = $2
        """,
        UUID(str(bundle_id)),
        UUID(str(user_id)),
    )


async def mark_bundle_access_success(conn, bundle_id, user_id) -> None:
    await conn.execute(
        """
        UPDATE bundle_access_control
        SET failed_attempts = 0,
            locked_until = NULL,
            first_success_at = COALESCE(first_success_at, now())
        WHERE bundle_id = $1 AND user_id = $2
        """,
        UUID(str(bundle_id)),
        UUID(str(user_id)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEXT FILE ACCESS CONTROL
# ─────────────────────────────────────────────────────────────────────────────

async def get_or_create_text_file_access(conn, file_id, user_id) -> dict:
    row = await conn.fetchrow(
        """
        SELECT failed_attempts, locked_until, first_success_at
        FROM bundle_text_file_access_control
        WHERE file_id = $1 AND user_id = $2
        """,
        UUID(str(file_id)),
        UUID(str(user_id)),
    )
    if not row:
        await conn.execute(
            "INSERT INTO bundle_text_file_access_control (file_id, user_id) VALUES ($1, $2)",
            UUID(str(file_id)),
            UUID(str(user_id)),
        )
        return {"failed_attempts": 0, "locked_until": None, "first_success_at": None}
    return dict(row)


async def increment_text_file_failed_attempt(conn, file_id, user_id) -> None:
    await conn.execute(
        """
        UPDATE bundle_text_file_access_control
        SET failed_attempts = failed_attempts + 1,
            last_failed_at = now(),
            locked_until = CASE
                WHEN failed_attempts + 1 >= 3 THEN now() + INTERVAL '10 minutes'
                ELSE locked_until
            END
        WHERE file_id = $1 AND user_id = $2
        """,
        UUID(str(file_id)),
        UUID(str(user_id)),
    )


async def mark_text_file_access_success(conn, file_id, user_id) -> None:
    await conn.execute(
        """
        UPDATE bundle_text_file_access_control
        SET failed_attempts = 0,
            locked_until = NULL,
            first_success_at = COALESCE(first_success_at, now())
        WHERE file_id = $1 AND user_id = $2
        """,
        UUID(str(file_id)),
        UUID(str(user_id)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# BINARY FILE ACCESS CONTROL
# ─────────────────────────────────────────────────────────────────────────────

async def get_or_create_binary_file_access(conn, file_id, user_id) -> dict:
    row = await conn.fetchrow(
        """
        SELECT failed_attempts, locked_until, first_success_at
        FROM bundle_binary_file_access_control
        WHERE file_id = $1 AND user_id = $2
        """,
        UUID(str(file_id)),
        UUID(str(user_id)),
    )
    if not row:
        await conn.execute(
            "INSERT INTO bundle_binary_file_access_control (file_id, user_id) VALUES ($1, $2)",
            UUID(str(file_id)),
            UUID(str(user_id)),
        )
        return {"failed_attempts": 0, "locked_until": None, "first_success_at": None}
    return dict(row)


async def increment_binary_file_failed_attempt(conn, file_id, user_id) -> None:
    await conn.execute(
        """
        UPDATE bundle_binary_file_access_control
        SET failed_attempts = failed_attempts + 1,
            last_failed_at = now(),
            locked_until = CASE
                WHEN failed_attempts + 1 >= 3 THEN now() + INTERVAL '10 minutes'
                ELSE locked_until
            END
        WHERE file_id = $1 AND user_id = $2
        """,
        UUID(str(file_id)),
        UUID(str(user_id)),
    )


async def mark_binary_file_access_success(conn, file_id, user_id) -> None:
    await conn.execute(
        """
        UPDATE bundle_binary_file_access_control
        SET failed_attempts = 0,
            locked_until = NULL,
            first_success_at = COALESCE(first_success_at, now())
        WHERE file_id = $1 AND user_id = $2
        """,
        UUID(str(file_id)),
        UUID(str(user_id)),
    )
