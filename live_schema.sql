--
-- PostgreSQL database dump
--

\restrict DS0EFhc14t9dOP7knrQBcJKYBivBp3ckrA5LBFvfFJs1cBjfKvvBTbUlJNdPG4g

-- Dumped from database version 15.15
-- Dumped by pg_dump version 15.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: anonymous_snippets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.anonymous_snippets (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    code_id text NOT NULL,
    encoded_content text NOT NULL,
    language text,
    highlights text,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.anonymous_snippets OWNER TO postgres;

--
-- Name: document_snapshots; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.document_snapshots (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    room_id uuid NOT NULL,
    content text NOT NULL,
    revision integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.document_snapshots OWNER TO postgres;

--
-- Name: operation_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.operation_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    room_id uuid NOT NULL,
    user_id uuid NOT NULL,
    op_id text NOT NULL,
    revision integer NOT NULL,
    op_type text NOT NULL,
    "position" integer NOT NULL,
    chars text,
    length integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_delete_has_length CHECK (((op_type <> 'delete'::text) OR ((length IS NOT NULL) AND (length > 0) AND (chars IS NULL)))),
    CONSTRAINT chk_insert_has_chars CHECK (((op_type <> 'insert'::text) OR ((chars IS NOT NULL) AND (length IS NULL)))),
    CONSTRAINT chk_op_type CHECK ((op_type = ANY (ARRAY['insert'::text, 'delete'::text])))
);


ALTER TABLE public.operation_log OWNER TO postgres;

--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.password_reset_tokens (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    used boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.password_reset_tokens OWNER TO postgres;

--
-- Name: room_join_requests; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.room_join_requests (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    room_id uuid NOT NULL,
    user_id uuid NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    requested_at timestamp without time zone DEFAULT now() NOT NULL,
    resolved_at timestamp without time zone,
    CONSTRAINT chk_join_status CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text])))
);


ALTER TABLE public.room_join_requests OWNER TO postgres;

--
-- Name: room_participants; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.room_participants (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    room_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role text DEFAULT 'participant'::text NOT NULL,
    is_muted boolean DEFAULT false NOT NULL,
    joined_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_participant_role CHECK ((role = ANY (ARRAY['host'::text, 'cohost'::text, 'participant'::text])))
);


ALTER TABLE public.room_participants OWNER TO postgres;

--
-- Name: rooms; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rooms (
    room_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    host_id uuid NOT NULL,
    title text NOT NULL,
    current_revision integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    is_locked boolean DEFAULT false NOT NULL,
    password_hash text,
    password_version integer DEFAULT 0 NOT NULL,
    cohost_id uuid,
    last_active_at timestamp without time zone DEFAULT now() NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.rooms OWNER TO postgres;

--
-- Name: snippet_access_control; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.snippet_access_control (
    snippet_id uuid NOT NULL,
    user_id uuid NOT NULL,
    failed_attempts integer DEFAULT 0,
    last_failed_at timestamp without time zone,
    locked_until timestamp without time zone,
    first_success_at timestamp without time zone
);


ALTER TABLE public.snippet_access_control OWNER TO postgres;

--
-- Name: user_snippets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_snippets (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    code_id text NOT NULL,
    owner_id uuid,
    encoded_content text NOT NULL,
    language text,
    highlights text,
    is_password_protected boolean DEFAULT false,
    password_hash text,
    expires_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    title text,
    CONSTRAINT chk_expiry_future CHECK ((expires_at > created_at)),
    CONSTRAINT chk_password_logic CHECK ((((is_password_protected = false) AND (password_hash IS NULL)) OR ((is_password_protected = true) AND (password_hash IS NOT NULL))))
);


ALTER TABLE public.user_snippets OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    user_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    username text
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: anonymous_snippets anonymous_snippets_code_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.anonymous_snippets
    ADD CONSTRAINT anonymous_snippets_code_id_key UNIQUE (code_id);


--
-- Name: anonymous_snippets anonymous_snippets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.anonymous_snippets
    ADD CONSTRAINT anonymous_snippets_pkey PRIMARY KEY (id);


--
-- Name: document_snapshots document_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.document_snapshots
    ADD CONSTRAINT document_snapshots_pkey PRIMARY KEY (id);


--
-- Name: document_snapshots document_snapshots_room_id_revision_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.document_snapshots
    ADD CONSTRAINT document_snapshots_room_id_revision_key UNIQUE (room_id, revision);


--
-- Name: operation_log operation_log_op_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operation_log
    ADD CONSTRAINT operation_log_op_id_key UNIQUE (op_id);


--
-- Name: operation_log operation_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operation_log
    ADD CONSTRAINT operation_log_pkey PRIMARY KEY (id);


--
-- Name: operation_log operation_log_room_id_revision_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operation_log
    ADD CONSTRAINT operation_log_room_id_revision_key UNIQUE (room_id, revision);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);


--
-- Name: room_join_requests room_join_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.room_join_requests
    ADD CONSTRAINT room_join_requests_pkey PRIMARY KEY (id);


--
-- Name: room_participants room_participants_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.room_participants
    ADD CONSTRAINT room_participants_pkey PRIMARY KEY (id);


--
-- Name: room_participants room_participants_room_id_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.room_participants
    ADD CONSTRAINT room_participants_room_id_user_id_key UNIQUE (room_id, user_id);


--
-- Name: rooms rooms_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (room_id);


--
-- Name: snippet_access_control snippet_access_control_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.snippet_access_control
    ADD CONSTRAINT snippet_access_control_pkey PRIMARY KEY (snippet_id, user_id);


--
-- Name: user_snippets user_snippets_code_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_snippets
    ADD CONSTRAINT user_snippets_code_id_key UNIQUE (code_id);


--
-- Name: user_snippets user_snippets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_snippets
    ADD CONSTRAINT user_snippets_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_access_snippet; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_access_snippet ON public.snippet_access_control USING btree (snippet_id);


--
-- Name: idx_access_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_access_user ON public.snippet_access_control USING btree (user_id);


--
-- Name: idx_anon_code_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX idx_anon_code_id ON public.anonymous_snippets USING btree (code_id);


--
-- Name: idx_join_requests_room; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_join_requests_room ON public.room_join_requests USING btree (room_id);


--
-- Name: idx_join_requests_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_join_requests_status ON public.room_join_requests USING btree (room_id, status);


--
-- Name: idx_join_requests_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_join_requests_user ON public.room_join_requests USING btree (user_id);


--
-- Name: idx_op_log_room_rev; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_op_log_room_rev ON public.operation_log USING btree (room_id, revision);


--
-- Name: idx_participants_room; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_participants_room ON public.room_participants USING btree (room_id);


--
-- Name: idx_participants_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_participants_user ON public.room_participants USING btree (user_id);


--
-- Name: idx_reset_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reset_user ON public.password_reset_tokens USING btree (user_id);


--
-- Name: idx_rooms_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_rooms_active ON public.rooms USING btree (is_active);


--
-- Name: idx_rooms_host; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_rooms_host ON public.rooms USING btree (host_id);


--
-- Name: idx_snapshots_room_rev; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_snapshots_room_rev ON public.document_snapshots USING btree (room_id, revision DESC);


--
-- Name: idx_user_code_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX idx_user_code_id ON public.user_snippets USING btree (code_id);


--
-- Name: idx_user_expiry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_expiry ON public.user_snippets USING btree (expires_at);


--
-- Name: idx_user_owner; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_owner ON public.user_snippets USING btree (owner_id);


--
-- Name: document_snapshots document_snapshots_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.document_snapshots
    ADD CONSTRAINT document_snapshots_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: operation_log operation_log_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operation_log
    ADD CONSTRAINT operation_log_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: operation_log operation_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operation_log
    ADD CONSTRAINT operation_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: password_reset_tokens password_reset_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: room_join_requests room_join_requests_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.room_join_requests
    ADD CONSTRAINT room_join_requests_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: room_join_requests room_join_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.room_join_requests
    ADD CONSTRAINT room_join_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: room_participants room_participants_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.room_participants
    ADD CONSTRAINT room_participants_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: room_participants room_participants_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.room_participants
    ADD CONSTRAINT room_participants_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: rooms rooms_cohost_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_cohost_id_fkey FOREIGN KEY (cohost_id) REFERENCES public.users(user_id) ON DELETE SET NULL;


--
-- Name: rooms rooms_host_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_host_id_fkey FOREIGN KEY (host_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: snippet_access_control snippet_access_control_snippet_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.snippet_access_control
    ADD CONSTRAINT snippet_access_control_snippet_id_fkey FOREIGN KEY (snippet_id) REFERENCES public.user_snippets(id) ON DELETE CASCADE;


--
-- Name: snippet_access_control snippet_access_control_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.snippet_access_control
    ADD CONSTRAINT snippet_access_control_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: user_snippets user_snippets_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_snippets
    ADD CONSTRAINT user_snippets_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict DS0EFhc14t9dOP7knrQBcJKYBivBp3ckrA5LBFvfFJs1cBjfKvvBTbUlJNdPG4g

