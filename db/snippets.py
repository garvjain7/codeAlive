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
    row = await conn.fetchrow(
        "SELECT *, 'anonymous' AS type FROM anonymous_snippets WHERE code_id=$1",
        code_id
    )
    if row:
        return dict(row)

    row = await conn.fetchrow(
        "SELECT *, 'user' AS type FROM user_snippets WHERE code_id=$1",
        code_id
    )
    return dict(row) if row else None
