"""
scripts/migrate_bundle_schema.py
---------------------------------
Migration: Drop old bundle_files + bundles tables (if exist),
create new 6-table bundle schema with UUID primary keys.
Run once against Neon DB.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DDL = """
-- Drop old tables if they exist (child tables first)
DROP TABLE IF EXISTS public.bundle_text_file_access_control CASCADE;
DROP TABLE IF EXISTS public.bundle_binary_file_access_control CASCADE;
DROP TABLE IF EXISTS public.bundle_access_control CASCADE;
DROP TABLE IF EXISTS public.bundle_text_files CASCADE;
DROP TABLE IF EXISTS public.bundle_binary_files CASCADE;
DROP TABLE IF EXISTS public.bundle_files CASCADE;
DROP TABLE IF EXISTS public.bundles CASCADE;

-- ── Parent bundle record ─────────────────────────────────────
CREATE TABLE public.bundles (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code                   VARCHAR(12) UNIQUE NOT NULL,
    owner_id               UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    title                  TEXT,
    bundle_type            VARCHAR(8) NOT NULL CHECK (bundle_type IN ('text', 'binary')),
    permission             VARCHAR(16) NOT NULL DEFAULT 'admin_only'
                           CHECK (permission IN ('admin_only', 'anyone')),
    expires_at             TIMESTAMPTZ,
    is_password_protected  BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash          TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT bundle_password_consistency
        CHECK (NOT is_password_protected OR password_hash IS NOT NULL)
);

CREATE INDEX idx_bundles_owner_id ON public.bundles (owner_id);


-- ── Text/code bundle files (mirrors user_snippets) ───────────
-- content is raw TEXT — OT engine reads/writes directly, no compression
CREATE TABLE public.bundle_text_files (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    bundle_id              UUID NOT NULL REFERENCES public.bundles(id) ON DELETE CASCADE,
    name                   VARCHAR(255) NOT NULL DEFAULT 'untitled',
    content                TEXT NOT NULL DEFAULT '',
    language               VARCHAR(32),
    position               SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 5),
    is_password_protected  BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash          TEXT,
    last_edited_by         UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bundle_id, position),
    CONSTRAINT bundle_text_file_password_consistency
        CHECK (NOT is_password_protected OR password_hash IS NOT NULL)
);


-- ── Binary bundle files (mirrors user_file_uploads) ──────────
-- file bytes stored in R2; file_id = R2 object key string
CREATE TABLE public.bundle_binary_files (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id                TEXT NOT NULL UNIQUE,
    bundle_id              UUID NOT NULL REFERENCES public.bundles(id) ON DELETE CASCADE,
    name                   VARCHAR(255) NOT NULL DEFAULT 'untitled',
    original_filename      TEXT NOT NULL,
    file_type              TEXT NOT NULL,
    file_size_bytes        INTEGER NOT NULL,
    position               SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 5),
    is_password_protected  BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash          TEXT,
    download_count         INTEGER NOT NULL DEFAULT 0,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bundle_id, position),
    CONSTRAINT bundle_binary_file_password_consistency
        CHECK (NOT is_password_protected OR password_hash IS NOT NULL)
);

CREATE INDEX idx_bundle_binary_files_bundle ON public.bundle_binary_files (bundle_id);


-- ── Bundle-level access control ───────────────────────────────
CREATE TABLE public.bundle_access_control (
    bundle_id              UUID NOT NULL REFERENCES public.bundles(id) ON DELETE CASCADE,
    user_id                UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    failed_attempts        INTEGER NOT NULL DEFAULT 0,
    last_failed_at         TIMESTAMPTZ,
    locked_until           TIMESTAMPTZ,
    first_success_at       TIMESTAMPTZ,
    PRIMARY KEY (bundle_id, user_id)
);

CREATE INDEX idx_bundle_access_bundle ON public.bundle_access_control (bundle_id);
CREATE INDEX idx_bundle_access_user   ON public.bundle_access_control (user_id);


-- ── Per-tab access control: text files ───────────────────────
CREATE TABLE public.bundle_text_file_access_control (
    file_id                UUID NOT NULL REFERENCES public.bundle_text_files(id) ON DELETE CASCADE,
    user_id                UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    failed_attempts        INTEGER NOT NULL DEFAULT 0,
    last_failed_at         TIMESTAMPTZ,
    locked_until           TIMESTAMPTZ,
    first_success_at       TIMESTAMPTZ,
    PRIMARY KEY (file_id, user_id)
);

CREATE INDEX idx_btf_access_file ON public.bundle_text_file_access_control (file_id);
CREATE INDEX idx_btf_access_user ON public.bundle_text_file_access_control (user_id);


-- ── Per-tab access control: binary files ─────────────────────
CREATE TABLE public.bundle_binary_file_access_control (
    file_id                UUID NOT NULL REFERENCES public.bundle_binary_files(id) ON DELETE CASCADE,
    user_id                UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    failed_attempts        INTEGER NOT NULL DEFAULT 0,
    last_failed_at         TIMESTAMPTZ,
    locked_until           TIMESTAMPTZ,
    first_success_at       TIMESTAMPTZ,
    PRIMARY KEY (file_id, user_id)
);

CREATE INDEX idx_bbf_access_file ON public.bundle_binary_file_access_control (file_id);
CREATE INDEX idx_bbf_access_user ON public.bundle_binary_file_access_control (user_id);
"""

VERIFY_QUERY = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'bundles',
    'bundle_text_files',
    'bundle_binary_files',
    'bundle_access_control',
    'bundle_text_file_access_control',
    'bundle_binary_file_access_control'
  )
ORDER BY table_name;
"""

async def run():
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise RuntimeError("DB_URL not set in environment")

    print("Connecting to Neon...")
    conn = await asyncpg.connect(db_url)

    try:
        print("Running migration...")
        await conn.execute(DDL)
        print("Migration complete.\n")

        rows = await conn.fetch(VERIFY_QUERY)
        found = [r["table_name"] for r in rows]
        expected = [
            "bundle_access_control",
            "bundle_binary_file_access_control",
            "bundle_binary_files",
            "bundle_text_file_access_control",
            "bundle_text_files",
            "bundles",
        ]

        print("Verifying tables:")
        all_ok = True
        for t in expected:
            status = "[OK]" if t in found else "[MISSING]"
            print(f"  {status}  {t}")
            if t not in found:
                all_ok = False

        print()
        if all_ok:
            print("All 6 tables created successfully on Neon.")
        else:
            print("Some tables are missing -- check errors above.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
