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

        await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_anon_file_id ON public.anonymous_file_uploads (file_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_file_expiry ON public.user_file_uploads (expires_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_file_owner ON public.user_file_uploads (owner_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_file_access_file ON public.file_access_control (file_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_file_access_user ON public.file_access_control (user_id)")

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
        min_size=20,
        max_size=100,
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
