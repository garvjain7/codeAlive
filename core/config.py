import os

# Feature Flag Toggles
# Set ENABLE_ROOMS=true in environment or change default to True when frontend Rooms UI is ready.
ENABLE_ROOMS: bool = os.getenv("ENABLE_ROOMS", "false").lower() in ("true", "1", "t", "yes")

# Remote API Proxy Configuration
REMOTE_API_MODE: bool = os.getenv("REMOTE_API_MODE", "false").lower() in ("true", "1", "t", "yes")
LIVE_API_URL: str = os.getenv("LIVE_API_URL", "https://codealive.onrender.com").rstrip("/")

