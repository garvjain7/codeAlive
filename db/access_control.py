async def get_or_create_access(conn, snippet_id, user_id):
    row = await conn.fetchrow("""
        SELECT * FROM snippet_access_control
        WHERE snippet_id=$1 AND user_id=$2
    """, snippet_id, user_id)

    if not row:
        await conn.execute("""
            INSERT INTO snippet_access_control (snippet_id, user_id)
            VALUES ($1, $2)
        """, snippet_id, user_id)

        return {
            "failed_attempts": 0,
            "locked_until": None,
            "first_success_at": None
        }

    return dict(row)

async def increment_failed_attempt(conn, snippet_id, user_id):
    await conn.execute("""
        UPDATE snippet_access_control
        SET failed_attempts = failed_attempts + 1,
            last_failed_at = NOW(),
            locked_until = CASE
                WHEN failed_attempts + 1 >= 3 THEN NOW() + INTERVAL '10 minutes'
                ELSE locked_until
            END
        WHERE snippet_id=$1 AND user_id=$2
    """, snippet_id, user_id)

async def mark_success(conn, snippet_id, user_id):
    await conn.execute("""
        UPDATE snippet_access_control
        SET failed_attempts = 0,
            locked_until = NULL,
            first_success_at = COALESCE(first_success_at, NOW())
        WHERE snippet_id=$1 AND user_id=$2
    """, snippet_id, user_id)
