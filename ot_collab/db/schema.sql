-- ================================
-- OT COLLABORATION TABLES
-- codealive-db
-- Run after existing schema.sql
-- ================================
-- Migration v2 notes at bottom.
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
    is_locked        BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash    TEXT,                          -- NULL = no password
    password_version INT NOT NULL DEFAULT 0,        -- incremented on every password change
    cohost_id        UUID REFERENCES users(user_id) ON DELETE SET NULL,
    last_active_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rooms_host   ON rooms(host_id);
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
    role      TEXT NOT NULL DEFAULT 'participant'
              CONSTRAINT chk_participant_role CHECK (role IN ('host', 'cohost', 'participant')),
    is_muted  BOOLEAN NOT NULL DEFAULT FALSE,
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
    status       TEXT NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMP,
    CONSTRAINT chk_join_status CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE INDEX idx_join_requests_room   ON room_join_requests(room_id);
CREATE INDEX idx_join_requests_user   ON room_join_requests(user_id);
CREATE INDEX idx_join_requests_status ON room_join_requests(room_id, status);

-- ================================
-- OPERATION LOG
-- ================================
-- UNIQUE(room_id, revision) — DB-level OT correctness guard.
-- UNIQUE(op_id)             — client retry idempotency guard.

CREATE TABLE operation_log (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id    UUID NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    op_id      TEXT NOT NULL,
    revision   INT NOT NULL,
    op_type    TEXT NOT NULL,
    position   INT NOT NULL,
    chars      TEXT,
    length     INT,
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

CREATE INDEX idx_op_log_room_rev ON operation_log(room_id, revision ASC);

-- ================================
-- DOCUMENT SNAPSHOTS
-- ================================

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
-- MIGRATION v2
-- ================================
-- If running against an existing v1 schema (rooms + room_participants
-- already exist without the new columns), run these ALTERs instead
-- of the full CREATE TABLE block above.
--
-- ALTER TABLE rooms
--     ADD COLUMN IF NOT EXISTS is_locked        BOOLEAN NOT NULL DEFAULT FALSE,
--     ADD COLUMN IF NOT EXISTS password_hash    TEXT,
--     ADD COLUMN IF NOT EXISTS password_version INT NOT NULL DEFAULT 0,
--     ADD COLUMN IF NOT EXISTS cohost_id        UUID REFERENCES users(user_id) ON DELETE SET NULL;
--
-- ALTER TABLE room_participants
--     ADD COLUMN IF NOT EXISTS role     TEXT NOT NULL DEFAULT 'participant',
--     ADD COLUMN IF NOT EXISTS is_muted BOOLEAN NOT NULL DEFAULT FALSE;
--
-- ALTER TABLE room_participants
--     ADD CONSTRAINT chk_participant_role
--     CHECK (role IN ('host', 'cohost', 'participant'));
-- ================================