import uuid

async def get_user_by_identifier(conn, identifier: str):
    """Fetch a user by email OR username."""
    row = await conn.fetchrow("""
        SELECT * FROM users WHERE email = $1 OR username = $1
    """, identifier)
    return dict(row) if row else None

async def get_user_by_id(conn, user_id: uuid.UUID):
    """Fetch a user by their primary key user_id."""
    row = await conn.fetchrow("""
        SELECT * FROM users WHERE user_id = $1
    """, user_id)
    return dict(row) if row else None

async def create_user(conn, username: str, email: str, password_hash: str):
    row = await conn.fetchrow("""
        INSERT INTO users (username, email, password_hash)
        VALUES ($1, $2, $3)
        RETURNING *
    """, username, email, password_hash)
    return dict(row)
