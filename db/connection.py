import asyncpg
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

pool = None

async def ensure_schema():
    if not pool:
        raise RuntimeError("Database pool is not initialized. Call connect_db() first.")

    async with pool.acquire() as conn:
        await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.anonymous_file_uploads (
            id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            file_id text NOT NULL UNIQUE,
            original_filename text NOT NULL,
            file_type text NOT NULL,
            file_size_bytes integer NOT NULL,
            created_at timestamp without time zone DEFAULT now()
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.user_file_uploads (
            id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            file_id text NOT NULL UNIQUE,
            owner_id uuid,
            title text NOT NULL,
            original_filename text NOT NULL,
            file_type text NOT NULL,
            file_size_bytes integer NOT NULL,
            is_password_protected boolean DEFAULT false,
            password_hash text,
            expires_at timestamp without time zone NOT NULL,
            download_count integer DEFAULT 0,
            created_at timestamp without time zone DEFAULT now(),
            CONSTRAINT chk_file_expiry_future CHECK ((expires_at > created_at)),
            CONSTRAINT chk_file_password_logic CHECK (
                (((is_password_protected = false) AND (password_hash IS NULL))
                OR ((is_password_protected = true) AND (password_hash IS NOT NULL)))
            )
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.file_access_control (
            file_id uuid NOT NULL,
            user_id uuid NOT NULL,
            failed_attempts integer DEFAULT 0,
            last_failed_at timestamp without time zone,
            locked_until timestamp without time zone,
            first_success_at timestamp without time zone,
            CONSTRAINT file_access_control_pkey PRIMARY KEY (file_id, user_id)
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.bundles (
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
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.bundle_text_files (
            id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            bundle_id              UUID NOT NULL REFERENCES public.bundles(id) ON DELETE CASCADE,
            code                   VARCHAR(32) NOT NULL,
            name                   VARCHAR(255) NOT NULL DEFAULT 'untitled',
            encoded_content        TEXT NOT NULL DEFAULT '',
            language               VARCHAR(32),
            position               SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 5),
            is_password_protected  BOOLEAN NOT NULL DEFAULT FALSE,
            password_hash          TEXT,
            last_edited_by         UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (bundle_id, position),
            UNIQUE (bundle_id, code),
            CONSTRAINT bundle_text_file_password_consistency
                CHECK (NOT is_password_protected OR password_hash IS NOT NULL)
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.bundle_binary_files (
            id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            file_id                TEXT NOT NULL UNIQUE,
            bundle_id              UUID NOT NULL REFERENCES public.bundles(id) ON DELETE CASCADE,
            code                   VARCHAR(32) NOT NULL,
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
            UNIQUE (bundle_id, code),
            CONSTRAINT bundle_binary_file_password_consistency
                CHECK (NOT is_password_protected OR password_hash IS NOT NULL)
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.bundle_access_control (
            bundle_id              UUID NOT NULL REFERENCES public.bundles(id) ON DELETE CASCADE,
            user_id                UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
            failed_attempts        INTEGER NOT NULL DEFAULT 0,
            last_failed_at         TIMESTAMPTZ,
            locked_until           TIMESTAMPTZ,
            first_success_at       TIMESTAMPTZ,
            PRIMARY KEY (bundle_id, user_id)
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.bundle_text_file_access_control (
            file_id                UUID NOT NULL REFERENCES public.bundle_text_files(id) ON DELETE CASCADE,
            user_id                UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
            failed_attempts        INTEGER NOT NULL DEFAULT 0,
            last_failed_at         TIMESTAMPTZ,
            locked_until           TIMESTAMPTZ,
            first_success_at       TIMESTAMPTZ,
            PRIMARY KEY (file_id, user_id)
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS public.bundle_binary_file_access_control (
            file_id                UUID NOT NULL REFERENCES public.bundle_binary_files(id) ON DELETE CASCADE,
            user_id                UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
            failed_attempts        INTEGER NOT NULL DEFAULT 0,
            last_failed_at         TIMESTAMPTZ,
            locked_until           TIMESTAMPTZ,
            first_success_at       TIMESTAMPTZ,
            PRIMARY KEY (file_id, user_id)
        )
        """)

        await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_anon_file_id ON public.anonymous_file_uploads (file_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_file_expiry ON public.user_file_uploads (expires_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_file_owner ON public.user_file_uploads (owner_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_file_access_file ON public.file_access_control (file_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_file_access_user ON public.file_access_control (user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bundles_owner_id ON public.bundles (owner_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bundle_binary_files_bundle ON public.bundle_binary_files (bundle_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bundle_access_bundle ON public.bundle_access_control (bundle_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bundle_access_user ON public.bundle_access_control (user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_btf_access_file ON public.bundle_text_file_access_control (file_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_btf_access_user ON public.bundle_text_file_access_control (user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bbf_access_file ON public.bundle_binary_file_access_control (file_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bbf_access_user ON public.bundle_binary_file_access_control (user_id)")


        await conn.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'user_file_uploads_owner_id_fkey'
            ) THEN
                ALTER TABLE public.user_file_uploads
                ADD CONSTRAINT user_file_uploads_owner_id_fkey
                FOREIGN KEY (owner_id) REFERENCES public.users (user_id) ON DELETE CASCADE;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'file_access_control_file_id_fkey'
            ) THEN
                ALTER TABLE public.file_access_control
                ADD CONSTRAINT file_access_control_file_id_fkey
                FOREIGN KEY (file_id) REFERENCES public.user_file_uploads (id) ON DELETE CASCADE;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'file_access_control_user_id_fkey'
            ) THEN
                ALTER TABLE public.file_access_control
                ADD CONSTRAINT file_access_control_user_id_fkey
                FOREIGN KEY (user_id) REFERENCES public.users (user_id) ON DELETE CASCADE;
            END IF;
        END $$;
        """)

async def connect_db():
    global pool
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise ValueError("DB_URL is missing in environment variables.")
    pool = await asyncpg.create_pool(
        db_url,
        min_size=2,           # small standing pool, avoids full suspend under light traffic
        max_size=20,
        max_inactive_connection_lifetime=300,  # 5 min — connections survive short gaps, close on real idle
        command_timeout=60
    )
    await ensure_schema()

@asynccontextmanager
async def get_conn():
    # return pool.acquire()
    async with pool.acquire() as conn:
        yield conn

async def close_db():
    global pool
    if pool:
        await pool.close()
