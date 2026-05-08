import redis.asyncio as aioredis
import os
from dotenv import load_dotenv

load_dotenv()

async_redis = aioredis.from_url(
    os.getenv("REDIS_URL"),
    decode_responses=True
)

# async_redis = aioredis.Redis(
#     host="localhost",
#     port=6379,
#     decode_responses=True
# )