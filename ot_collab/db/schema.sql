-- ================================
-- OT COLLABORATION TABLES
-- codealive-db
-- Run after existing schema.sql
-- ================================

-- ================================
-- ROOMS
-- ================================

CREATE TABLE rooms (
    room_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    host_id          UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title            TEXT NOT NULL,
    current_revision INT NOT NULL DEFAULT 0,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_active_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rooms_host ON rooms(host_id);
CREATE INDEX idx_rooms_active ON rooms(is_active);

-- ================================
-- ROOM PARTICIPANTS
-- ================================
-- UNIQUE(room_id, user_id) makes add_participant
-- idempotent on reconnect — INSERT ... ON CONFLICT DO NOTHING

CREATE TABLE room_participants (
    id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id   UUID NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    user_id   UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    joined_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(room_id, user_id)
);

CREATE INDEX idx_participants_room ON room_participants(room_id);
CREATE INDEX idx_participants_user ON room_participants(user_id);

-- ================================
-- ROOM JOIN REQUESTS
-- ================================

CREATE TABLE room_join_requests (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id      UUID NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
    requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMP,
    CONSTRAINT chk_join_status CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE INDEX idx_join_requests_room ON room_join_requests(room_id);
CREATE INDEX idx_join_requests_user ON room_join_requests(user_id);
CREATE INDEX idx_join_requests_status ON room_join_requests(room_id, status);

-- ================================
-- OPERATION LOG
-- ================================
-- UNIQUE(room_id, revision) is the DB-level OT correctness guard.
-- Two ops cannot claim the same revision in the same room.
-- If this constraint fires it means a bug in room_state.py's Redis lock.
--
-- UNIQUE(op_id) is the idempotency guard.
-- Client retries are safe — second insert is silently ignored.

CREATE TABLE operation_log (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id    UUID NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    op_id      TEXT NOT NULL,           -- client-generated UUID, idempotency key
    revision   INT NOT NULL,            -- server revision AFTER this op applied
    op_type    TEXT NOT NULL,           -- 'insert' | 'delete'
    position   INT NOT NULL,
    chars      TEXT,                    -- insert only, NULL for delete
    length     INT,                     -- delete only, NULL for insert
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_op_type CHECK (op_type IN ('insert', 'delete')),
    CONSTRAINT chk_insert_has_chars CHECK (
        op_type != 'insert' OR (chars IS NOT NULL AND length IS NULL)
    ),
    CONSTRAINT chk_delete_has_length CHECK (
        op_type != 'delete' OR (length IS NOT NULL AND length > 0 AND chars IS NULL)
    ),
    UNIQUE(op_id),
    UNIQUE(room_id, revision)
);

-- Hot path: fetching history since revision N for transform catchup
CREATE INDEX idx_op_log_room_rev ON operation_log(room_id, revision ASC);

-- ================================
-- DOCUMENT SNAPSHOTS
-- ================================
-- Written every SNAPSHOT_EVERY_N_OPS (50) or on room close.
-- Recovery = latest snapshot + replay operation_log since that revision.
-- DESC index because we always want the latest snapshot first.

CREATE TABLE document_snapshots (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id    UUID NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    content    TEXT NOT NULL,
    revision   INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(room_id, revision)
);

CREATE INDEX idx_snapshots_room_rev ON document_snapshots(room_id, revision DESC);

-- ================================
-- DONE
-- ================================
-- New tables:
--   rooms
--   room_participants
--   room_join_requests
--   operation_log
--   document_snapshots
--
-- All foreign keys reference users(user_id) — consistent with existing schema.
-- All timestamps use TIMESTAMP — consistent with existing schema.
-- uuid_generate_v4() used — consistent with existing schema.