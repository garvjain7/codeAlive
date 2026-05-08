import asyncpg
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

pool = None

async def connect_db():
    global pool
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise ValueError("DB_URL is missing in environment variables.")
    pool = await asyncpg.create_pool(
        db_url,
        min_size=20,
        max_size=100,
        command_timeout=60
    )

@asynccontextmanager
async def get_conn():
    # return pool.acquire()
    async with pool.acquire() as conn:
        yield conn

async def close_db():
    global pool
    if pool:
        await pool.close()
