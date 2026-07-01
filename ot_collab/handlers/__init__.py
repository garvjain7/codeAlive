"""
ot_collab/handlers/__init__.py
-------------------------------
Re-exports all handler coroutines so ws_router.py imports cleanly
from a single location.
"""

from .ops import handle_op, handle_cursor
from .joins import run_password_gate, run_join_flow, handle_approval
from .moderation import (
    handle_kick,
    handle_mute,
    handle_unmute,
    handle_promote_cohost,
    handle_demote_cohost,
)
from .room_control import (
    handle_lock_room,
    handle_unlock_room,
    handle_set_password,
    handle_close_room,
)