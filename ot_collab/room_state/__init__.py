"""
ot_collab/room_state/__init__.py
---------------------------------
Re-exports all public functions from the room_state submodule.

Any code that previously imported from ot_collab.room_state continues
to work unchanged. The split into document/presence/room_meta/auth_cache
is an internal organization concern only.
"""

from .document import (
    init_document,
    get_room_doc,
    room_exists_in_redis,
    get_history_since,
    apply_op_to_room,
    expire_document_keys,
)

from .presence import (
    add_user_to_room,
    remove_user_from_room,
    get_user_state,
    get_room_users,
    get_existing_colors,
    update_user_cursor,
    set_user_muted,
    set_user_role,
    is_user_muted,
    get_user_role,
    expire_presence_key,
)

from .room_meta import (
    init_room_meta,
    get_room_host,
    set_room_host,
    get_room_cohost,
    set_room_cohost,
    clear_room_cohost,
    is_room_locked,
    set_room_locked,
    get_password_version,
    increment_password_version,
    set_password_version,
    set_host_grace,
    get_host_grace,
    clear_host_grace,
    scan_grace_keys,
    expire_meta_keys,
)

from .auth_cache import (
    set_room_auth,
    get_room_auth,
    revoke_room_auth,
    expire_all_auth_keys,
)


# ── Composite operations ───────────────────────────────────────────────────────
# These coordinate across submodules and live here to avoid circular imports.

async def init_room_in_redis(
    room_id:          str,
    content:          str,
    revision:         int,
    host_id:          str,
    cohost_id:        str | None = None,
    is_locked:        bool = False,
    password_version: int = 0,
) -> None:
    """
    Full room initialization in Redis.
    Called on room creation and on cold-start recovery from PostgreSQL.
    Coordinates document + presence (cleared) + meta seeding.
    """
    await init_document(room_id, content, revision)
    await init_room_meta(room_id, host_id, cohost_id, is_locked, password_version)
    # Presence hash is NOT seeded here — users populate it as they join.


async def expire_room(room_id: str) -> None:
    """
    Fully expire all Redis keys for a room.
    Called on room close or when the last user leaves.
    """
    await expire_document_keys(room_id)
    await expire_presence_key(room_id)
    await expire_meta_keys(room_id)