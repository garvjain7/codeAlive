import redis.asyncio as aioredis
import os
from dotenv import load_dotenv

load_dotenv()

async_redis = aioredis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379"),
    decode_responses=True
)