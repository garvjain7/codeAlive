import asyncpg
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

pool = None

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD"),
        database=os.getenv("PG_DB"),
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432))
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
