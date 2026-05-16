import asyncio
import asyncpg
import redis
import os
from dotenv import load_dotenv
from app import _parse_stored

load_dotenv()

async def migrate():
    # Connect to PostgreSQL
    try:
        pool = await asyncpg.create_pool(
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", "postgres"),
            database=os.getenv("PG_DB", "codealive-db"),
            host=os.getenv("PG_HOST", "localhost"),
            port=int(os.getenv("PG_PORT", 5432))
        )
    except Exception as e:
        print(f"Error connecting to Postgres: {e}")
        return

    # Connect to Redis
    try:
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)
        r.ping()
    except Exception as e:
        print(f"Error connecting to Redis: {e}")
        return

    print("Connected to both databases.")

    # Get all keys from Redis
    # In a large DB we would use SCAN, but keys() is fine for typical small instances
    keys = r.keys("*")
    if not keys:
        print("No keys found in Redis.")
        return

    migrated_count = 0
    skipped_count = 0

    async with pool.acquire() as conn:
        for key in keys:
            # Skip if the key is somehow one of our metadata/cache keys
            # (though the current app just stores code_ids)
            val = r.get(key)
            if not val:
                continue

            try:
                encoded, language, highlights = _parse_stored(val)
                
                await conn.execute("""
                    INSERT INTO anonymous_snippets (code_id, encoded_content, language, highlights)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (code_id) DO NOTHING
                """, key, encoded, language, highlights)
                
                migrated_count += 1
            except Exception as e:
                print(f"Failed to migrate key {key}: {e}")
                skipped_count += 1

    print(f"Migration complete. Migrated: {migrated_count}, Skipped/Failed: {skipped_count}")

if __name__ == "__main__":
    asyncio.run(migrate())
