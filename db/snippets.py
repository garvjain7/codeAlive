async def create_anonymous(conn, code_id, encoded_content, language, highlights):
    await conn.execute("""
        INSERT INTO anonymous_snippets (code_id, encoded_content, language, highlights)
        VALUES ($1, $2, $3, $4)
    """, code_id, encoded_content, language, highlights)

async def create_user_snippet(conn, code_id, owner_id, encoded_content, language, highlights, password_hash, expires_at, title=None):
    await conn.execute("""
        INSERT INTO user_snippets (
            code_id, owner_id, encoded_content, language, highlights,
            is_password_protected, password_hash, expires_at, title
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """,
    code_id, owner_id, encoded_content, language, highlights,
    password_hash is not None, password_hash, expires_at, title)

async def get_snippet_by_code_id(conn, code_id):
    """
    Fetch a snippet by code_id from either anonymous or user tables in a SINGLE query.
    This reduces database round-trips and improves TTFB.
    """
    row = await conn.fetchrow("""
        SELECT id, code_id, encoded_content, language, highlights, 'anonymous' AS type, 
               NULL::uuid AS owner_id, NULL::timestamp AS expires_at, NULL::boolean AS is_password_protected, 
               NULL::text AS password_hash, NULL::text AS title, created_at
        FROM anonymous_snippets WHERE code_id = $1
        UNION ALL
        SELECT id, code_id, encoded_content, language, highlights, 'user' AS type, 
               owner_id, expires_at, is_password_protected, 
               password_hash, title, created_at
        FROM user_snippets WHERE code_id = $1
        LIMIT 1
    """, code_id)
    return dict(row) if row else None
