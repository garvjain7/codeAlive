import os

# Feature Flag Toggles
# Set ENABLE_ROOMS=true in environment or change default to True when frontend Rooms UI is ready.
ENABLE_ROOMS: bool = os.getenv("ENABLE_ROOMS", "false").lower() in ("true", "1", "t", "yes")



