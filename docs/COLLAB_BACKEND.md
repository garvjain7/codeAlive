# CodeAlive — Collaboration Backend Architecture

## Overview

Real-time collaborative code editing built on Operational Transformation (OT).
Single Render instance. FastAPI + asyncio. Redis for live state. PostgreSQL for durability.

---

## File Structure

```
ot_collab/
├── models.py               All enums, dataclasses, MsgType constants
├── permissions.py          Pure role-based permission logic (no I/O)
├── password_utils.py       bcrypt helpers for room passwords
├── room_service.py         Multi-store coordination (PG + Redis)
├── grace_sweeper.py        Background task — closes rooms after host grace expires
├── connection_manager.py   In-process WebSocket registry
├── ws_router.py            FastAPI router — HTTP endpoints + WS dispatcher
├── ot_engine.py            Pure OT math (transform, apply, compose)
│
├── room_state/             Redis state layer — split by domain
│   ├── __init__.py         Re-exports all functions (backward compat)
│   ├── document.py         Doc content, revision, history, apply_op
│   ├── presence.py         Users hash — username, color, cursor, role, is_muted
│   ├── room_meta.py        Host, cohost, lock, grace period, password version
│   └── auth_cache.py       Per-user room password authorization cache
│
├── handlers/               Message handlers — one file per concern
│   ├── __init__.py         Re-exports all handlers
│   ├── ops.py              handle_op, handle_cursor
│   ├── joins.py            Password gate, join flow, approval signals
│   ├── moderation.py       Kick, mute, unmute, promote, demote
│   └── room_control.py     Lock, unlock, set password, close room
│
└── db/
    ├── schema.sql          PostgreSQL schema (v1 + v2 migration ALTERs)
    ├── rooms.py            PG queries — rooms, participants, join requests
    └── operations.py       PG queries — operation_log, snapshots, recovery
```

---

## Authority Model

**PostgreSQL is the durable authority for all persistent state.**
**Redis is a rebuild-able cache for live collaboration state.**

| State | Redis | PostgreSQL | Notes |
|---|---|---|---|
| Document content | ✓ live | ✓ snapshots | PG is authority |
| Revision | ✓ live | ✓ | Both kept in sync |
| Operation history | ✓ list | ✓ operation_log | Redis is hot path, PG for recovery |
| Cursor position | ✓ only | ✗ | Ephemeral, not persisted |
| User color | ✓ only | ✗ | Ephemeral, reassigned on rejoin |
| role | ✓ cache | ✓ authority | Seeded from PG at join time |
| is_muted | ✓ cache | ✓ authority | Seeded from PG at join time |
| is_locked | ✓ cache | ✓ authority | Restored on cold-start recovery |
| cohost_id | ✓ cache | ✓ authority | Restored on cold-start recovery |
| password_hash | PG only | ✓ authority | Never cached in Redis |
| password_version | ✓ cache | ✓ authority | Used for auth cache invalidation |
| Auth cache | ✓ only | ✗ | Intentionally ephemeral |
| Grace period timer | ✓ only | ✗ | Ephemeral timer |

**On cold-start recovery** (`db/operations.py:recover_room_state`):
- Document: rebuilt from latest snapshot + replay of operation_log
- Room metadata (locked, cohost, password_version): read directly from rooms table
- User presence: rebuilt per-user as they reconnect (role + is_muted from room_participants)

---

## Redis Key Space

```
room:{room_id}:doc              STRING   current document content
room:{room_id}:rev              STRING   current revision (int as string)
room:{room_id}:history          LIST     {revision, op} JSON entries
room:{room_id}:users            HASH     user_id → {username,color,line,col,role,is_muted}
room:{room_id}:host             STRING   host user_id
room:{room_id}:cohost           STRING   cohost user_id (absent if none)
room:{room_id}:locked           STRING   "1" if locked (absent if not)
room:{room_id}:password_version STRING   int, incremented on every password change
room:{room_id}:host_grace_until STRING   Unix timestamp float (absent if no grace)
room:{room_id}:auth:{user_id}   STRING   {expires_at, password_version} JSON
```

All room keys use TTL = `ROOM_TTL_SECONDS` (86400s = 24h), refreshed on every op.
Auth cache keys use TTL = min(24h, ROOM_TTL_SECONDS).
Grace key TTL = GRACE_PERIOD_SECONDS + 60s (sweeper is the real enforcement).

---

## PostgreSQL Schema

### `rooms`
| Column | Type | Notes |
|---|---|---|
| room_id | UUID PK | |
| host_id | UUID FK → users | |
| title | TEXT | |
| current_revision | INT | Synced from Redis on snapshot |
| is_active | BOOLEAN | FALSE = closed |
| is_locked | BOOLEAN | No new joins if TRUE |
| password_hash | TEXT nullable | NULL = no password |
| password_version | INT | Incremented on every password change |
| cohost_id | UUID FK → users nullable | ON DELETE SET NULL |
| last_active_at | TIMESTAMP | |
| created_at | TIMESTAMP | |

### `room_participants`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| room_id | UUID FK → rooms | |
| user_id | UUID FK → users | |
| role | TEXT | host / cohost / participant |
| is_muted | BOOLEAN | |
| joined_at | TIMESTAMP | |
| UNIQUE | (room_id, user_id) | Idempotent on reconnect |

### `room_join_requests`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| room_id | UUID FK | |
| user_id | UUID FK | |
| status | TEXT | pending / approved / rejected |
| requested_at | TIMESTAMP | |
| resolved_at | TIMESTAMP nullable | |

### `operation_log`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| room_id | UUID FK | |
| user_id | UUID FK | |
| op_id | TEXT | Client-generated UUID — idempotency key |
| revision | INT | Server revision AFTER this op applied |
| op_type | TEXT | insert / delete |
| position | INT | |
| chars | TEXT nullable | Insert only |
| length | INT nullable | Delete only |
| created_at | TIMESTAMP | |
| UNIQUE | (op_id) | Client retry idempotency |
| UNIQUE | (room_id, revision) | OT correctness guard |

### `document_snapshots`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| room_id | UUID FK | |
| content | TEXT | |
| revision | INT | |
| created_at | TIMESTAMP | |
| UNIQUE | (room_id, revision) | |

---

## Permission Matrix

| Action | host | cohost | participant |
|---|---|---|---|
| Send ops | ✓ | ✓ | ✓ (if not muted) |
| Send cursor | ✓ | ✓ | ✓ |
| Approve/reject joins | ✓ | ✓ | ✗ |
| Kick participant | ✓ | ✓ | ✗ |
| Mute / unmute | ✓ | ✓ | ✗ |
| Lock / unlock room | ✓ | ✓ | ✗ |
| Promote to cohost | ✓ | ✗ | ✗ |
| Demote cohost | ✓ | ✗ | ✗ |
| Set / clear password | ✓ | ✗ | ✗ |
| Close room | ✓ | ✗ | ✗ |

All permission checks go through `permissions.py` — never inline string comparisons.

---

## WebSocket Message Protocol

### Client → Server

| type | fields | who can send |
|---|---|---|
| op | op_id, room_id, op{}, client_revision | any (if not muted) |
| cursor | room_id, line, col | any |
| password_submit | room_id, password | joining user |
| approve_user | target_user_id, room_id, request_id | host / cohost |
| reject_user | target_user_id, room_id, request_id | host / cohost |
| kick_user | target_user_id, room_id | host / cohost |
| mute_user | target_user_id, room_id | host / cohost |
| unmute_user | target_user_id, room_id | host / cohost |
| promote_cohost | target_user_id, room_id | host |
| demote_cohost | target_user_id, room_id | host |
| lock_room | room_id | host / cohost |
| unlock_room | room_id | host / cohost |
| set_password | room_id, password (nullable) | host |
| close_room | room_id | host |

### Server → Client

| type | fields | direction |
|---|---|---|
| op_ack | op_id, revision, op{} | → sender |
| op_broadcast | op{}, revision, user_id | → others |
| cursor_broadcast | user_id, line, col | → others |
| password_required | — | → joining user |
| password_accepted | — | → joining user |
| password_rejected | message | → joining user |
| join_request | user_id, username, request_id | → host/cohost |
| join_approved | content, revision, users[], your_role | → joining user |
| join_rejected | message | → joining user |
| participant_joined | user_id, username, color, role | → all |
| participant_left | user_id | → all |
| you_were_kicked | message | → kicked user |
| participant_kicked | user_id | → all |
| you_were_muted | message | → muted user |
| participant_muted | user_id | → all |
| you_were_unmuted | message | → unmuted user |
| participant_unmuted | user_id | → all |
| cohost_promoted | user_id | → all |
| cohost_demoted | user_id | → all |
| room_locked | locked_by | → all |
| room_unlocked | — | → all |
| room_closed | — | → all |
| password_changed | has_password, password_version | → all |
| host_disconnected | grace_until (timestamp) | → all |
| host_rejoined | — | → all |
| host_grace_expired | message | → all |
| error | code, message | → sender |

---

## Join Flow

```
Client connects WS
        ↓
Auth (session_id → user_id)
        ↓
Load room from PG — is_active check
        ↓
Ensure Redis warm (cold-start recovery if needed)
        ↓
Password gate? (if room.password_hash AND not host)
  → check auth cache (room:{room_id}:auth:{user_id})
      → cache hit + version match → skip
      → cache miss → send PASSWORD_REQUIRED → wait for PASSWORD_SUBMIT
          → bcrypt verify → correct → cache auth → continue
          → wrong → close 4003
        ↓
Lock check? (if room.is_locked AND not host AND not cohost)
  → existing participant → allow reconnect
  → new user → close 4010
        ↓
is_participant check (PG)
  → YES (reconnect) → skip join flow
  → NO → run_join_flow:
      create join request in PG
      notify host (or cohost if host offline)
      wait for approval (asyncio.Event, 120s timeout)
          → approved → add_participant PG → continue
          → rejected / timeout → close 4003
        ↓
Seed Redis presence (role + is_muted from PG)
Register WS connection
Send JOIN_APPROVED (content, revision, users[], your_role)
Broadcast PARTICIPANT_JOINED to room
Enter relay loop
```

---

## Host Disconnect Lifecycle

```
Host WS closes (no CLOSE_ROOM message)
        ↓
finally block in ws_router:
  manager.disconnect()
  room_state.remove_user_from_room()
  room_service.handle_host_disconnect():
    → save snapshot to PG
    → set room:{room_id}:host_grace_until = now + 300s
  broadcast HOST_DISCONNECTED {grace_until}
        ↓
All participants: editing locked (handle_op checks get_host_grace)
        ↓
        ├── Host reconnects within 300s:
        │     ws_router detects grace key on join
        │     room_service.handle_host_rejoin() → clear grace key
        │     broadcast HOST_REJOINED
        │     editing unlocked
        │
        └── 300s expires:
              grace_sweeper._sweep() detects expired key
              save final snapshot
              set_room_inactive in PG
              broadcast HOST_GRACE_EXPIRED
              expire_room (all Redis keys deleted)
```

---

## Snapshot Strategy

- Written every `SNAPSHOT_EVERY_N_OPS` (50) operations — background task, not on critical path
- Written on host voluntary close (`CLOSE_ROOM` message)
- Written on host disconnect (immediately, before grace period starts)
- Written when last participant leaves
- Written by grace_sweeper when grace period expires
- Recovery: latest snapshot + replay operation_log since that revision

---

## OT Critical Path (per keystroke)

```
handle_op():
  1. parse ClientOpMessage
  2. is_user_muted()    → Redis HGET (single field)
  3. get_host_grace()   → Redis GET
  4. get_history_since() → Redis LRANGE
  5. transform_against_many() → pure Python
  6. apply_op_to_room() → Redis WATCH/GET/GET/SET/SET/RPUSH/EXPIRE×3
  7. send OP_ACK        → WebSocket
  8. broadcast          → WebSocket × N
  9. [background] persist_op → PG INSERT
 10. [background] save_snapshot → PG INSERT (every 50 ops)
```

Steps 1–8 are on the critical path. Steps 9–10 are background tasks.
No PG reads on the hot path.

---

## Grace Sweeper Registration

In `main.py` / `app.py`:

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from ot_collab.grace_sweeper import start_grace_sweeper

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(start_grace_sweeper())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
```

---

## Future: Images and Highlights

**Images** — no new WS protocol needed.
Upload via HTTP POST → get back `img_xxx` reference → insert as text op `[image:img_xxx]`.
All clients receive a standard OT insert op. CM6 MatchDecorator renders pill.
The OT system treats it as a regular string — zero special handling.

**Highlights / annotations** — ephemeral presence layer (future).
New message types: `highlight_set`, `highlight_clear`.
Stored in Redis like cursor data (not persisted to PG).
Broadcast to all, rendered as CM6 decorations.
Not part of OT — pure presence.

---

## Known Constraints

- **Single Render instance**: `connection_manager.py` is in-process. `_pending_join_events` in `handlers/joins.py` is in-process. Both break on horizontal scale. Documented for when you add a second instance: replace broadcast with Redis pub/sub, replace join events with a Redis-backed signaling mechanism.
- **BackgroundTasks in WS context**: FastAPI's `BackgroundTasks` in a WebSocket handler run when the handler returns (connection closes), not after each message. For true background execution of persist_op, use `asyncio.create_task()` instead if this becomes an issue.
- **No heartbeat**: Silent disconnects (mobile, flaky network) aren't detected until the next send fails. Add a ping/pong loop if this becomes a problem.