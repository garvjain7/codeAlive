import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

load_dotenv()


# ── Connection ────────────────────────────────────────────────────────────────
#
#  Reads MONGO_URI and MONGO_DB_NAME from environment variables.
#  Locally: set these in a .env file (loaded manually or via python-dotenv).
#  On Render: set them in the Environment tab.

MONGO_URI     = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "codealive")

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI environment variable is not set. "
        "Add it to your .env file locally or Render environment tab."
    )

_client = MongoClient(MONGO_URI)
db      = _client[MONGO_DB_NAME]

# ── Collections ───────────────────────────────────────────────────────────────

images_collection = db["snippet_images"]
waitlist_collection = db["waitlist"]

# ── Indexes (run once on startup — idempotent) ────────────────────────────────
#
#  created_at index → used for FIFO eviction (find oldest first)
#  email index → unique index for waitlist duplicates

images_collection.create_index("created_at")
waitlist_collection.create_index("email", unique=True)
waitlist_collection.create_index("joined_at")

print(f"[OK] MongoDB connected — database: {MONGO_DB_NAME}")