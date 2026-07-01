import sys
import os

# Add the root directory to sys.path
sys.path.append(os.getcwd())

from app import app

print("Mounted Routes:")
for route in app.routes:
    if hasattr(route, "path"):
        print(f"  {route.path} - {route.name}")
