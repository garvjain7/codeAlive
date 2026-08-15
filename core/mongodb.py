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

from core.config import REMOTE_API_MODE

MONGO_URI     = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "codealive")

if not MONGO_URI:
    if REMOTE_API_MODE:
        print("[REMOTE PROXY MODE] Skipping local MongoDB connection.")
        class DummyCollection:
            def create_index(self, *args, **kwargs): pass
            def find_one(self, *args, **kwargs): return None
            def insert_one(self, *args, **kwargs): return None
        images_collection = DummyCollection()
        waitlist_collection = DummyCollection()
    else:
        raise RuntimeError(
            "MONGO_URI environment variable is not set. "
            "Add it to your .env file locally or Render environment tab."
        )
else:
    _client = MongoClient(MONGO_URI)
    db      = _client[MONGO_DB_NAME]
    images_collection = db["snippet_images"]
    waitlist_collection = db["waitlist"]
    images_collection.create_index("created_at")
    waitlist_collection.create_index("email", unique=True)
    waitlist_collection.create_index("joined_at")
    print(f"[OK] MongoDB connected — database: {MONGO_DB_NAME}")