# CodeAlive — Bundle Sharing Feature

Status: design locked, not yet implemented
Last updated: 2026-08-16

## What this is

A shareable "bundle" of up to 5 text/code files under one link, live-editable
by multiple users at once. Inspired by Google Sheets: one URL, multiple
tabs (files) inside it, opens directly into the first file rather than a
folder/listing view.

Not related to the earlier Path A / Path B file-upload plan (CM6 text-save
vs. R2 binary storage) — bundles are a separate feature, files live directly
in `bundle_files`, not in the existing snippet/upload tables.

## Access model

- Bundles are created and opened only by **logged-in users**. No anonymous
  bundle creation or access.
- One shareable link per bundle: `/b/{code}`.
- No invite/ACL system. No `bundle_collaborators` table. Link + login is the
  entire access model — same "anyone with the link" pattern as the rest of
  CodeAlive's sharing, not a Google Docs "share with specific people" model.
- No revocation beyond dropping permission to `admin_only`. No link
  regeneration (out of scope for now, one-line addition later if needed).

## Permission model

Exactly two values on `bundles.permission`:

- `admin_only` — only the bundle owner can edit content, rename files, add
  files, remove files, or change permission.
- `anyone` — any authenticated user holding the link can edit content and
  rename files. **Delete, add-file, and permission-change stay owner-gated
  regardless of this value.** `anyone` governs edit, not structure.

## Schema

```sql
-- ============================================================
-- BUNDLES
-- ============================================================
CREATE TABLE bundles (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(12) UNIQUE NOT NULL,                 -- shareable link identifier
    owner_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,  -- matches live schema's users.user_id type
    permission  VARCHAR(16) NOT NULL DEFAULT 'admin_only'
                CHECK (permission IN ('admin_only', 'anyone')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bundles_owner_id ON bundles (owner_id);
-- bundles.code already indexed via UNIQUE constraint


-- ============================================================
-- BUNDLE FILES
-- ============================================================
CREATE TABLE bundle_files (
    id              SERIAL PRIMARY KEY,
    bundle_id       INTEGER NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL DEFAULT 'untitled',
    content         TEXT NOT NULL DEFAULT '',
    language        VARCHAR(32),                             -- resolved from name/extension, drives CM6 mode
    position        SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 5),
    last_edited_by  UUID REFERENCES users(user_id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (bundle_id, position)
);
-- (bundle_id, position) UNIQUE already covers "fetch all files for bundle, ordered"
```

**`owner_id ON DELETE CASCADE` — confirm this is intentional.** Deleting a user
will delete every bundle they own, including all files inside. If that's not
the desired behavior, switch to `ON DELETE RESTRICT` (block user deletion
while they still own bundles) or add an ownership-reassignment step instead.
Not yet confirmed as of last update — currently written as CASCADE per the
UUID-type fix, but this was a side effect of that fix, not a deliberate
choice, and needs a decision.

Deliberately self-contained: `bundle_files` does **not** FK into any existing
snippet/file table. Bundle files aren't independently shareable outside their
bundle, so there's no case requiring content to live in two places.

Column name `code` is reused from the existing snippet-share table
intentionally — no conflict, independent tables, and route prefixes
(`/s/{code}` vs `/b/{code}`) already disambiguate, so no cross-table
uniqueness check is needed at generation time.

No soft delete anywhere — hard delete only. Nothing in this feature reads
deleted rows back (no trash/undo/history UI), so a `deleted_at` column would
have no consumer.

No `last_edited_by` index — no query pattern ("all files last edited by
user X") currently needs it. Add only if that query shows up.

No OT/version columns in Postgres. Version/revision state for conflict
resolution lives transiently in Redis room state, not persisted — the schema
only needs to know current content + who touched it last + when, regardless
of whether the write came from a plain PATCH or an OT flush.

## Endpoints

```
POST   /bundle                     create (files[], permission) -> { code }
GET    /b/{code}                   fetch bundle metadata + all file contents,
                                    ordered by position; frontend renders
                                    position=1 immediately, other 4 as tabs
PATCH  /b/{code}/files/{file_id}   rename (name field) — direct PATCH.
                                    content is NOT written here during a live
                                    session (see OT section) — this path is
                                    only for rename, or as the OT flush target.
POST   /b/{code}/files             add file, 403 if count == 5,
                                    owner-only regardless of permission value
DELETE /b/{code}/files/{file_id}   remove file, owner-only regardless of
                                    permission value, hard delete
PATCH  /b/{code}/permission        owner-only, flip admin_only ↔ anyone
```

`file_id` = `bundle_files.id`. `code` identifies the bundle and never
changes; all 5 files under a bundle share one `code`.

## Delete behavior

Owner-only, hard delete, transactional:

1. Verify `req.user.id === bundle.owner_id`.
2. `DELETE FROM bundle_files WHERE id = $1`.
3. Shift positions down in the same transaction. A single
   `UPDATE ... SET position = position - 1 WHERE position > $deleted_position`
   can transiently collide with the `UNIQUE (bundle_id, position)` constraint
   depending on the order Postgres processes rows in. Use a two-pass shift
   instead — push affected rows negative first (guaranteed no collision with
   remaining positive positions), then resolve to final values:
   ```sql
   UPDATE bundle_files SET position = -position
     WHERE bundle_id = $1 AND position > $deleted_position;
   UPDATE bundle_files SET position = -position - 1
     WHERE bundle_id = $1 AND position < 0;
   ```
4. Reject if it's the last remaining file in the bundle (bundle needs ≥1 file).

Positions stay contiguous (1..N) — simpler for the tab strip and for the
`CHECK (position BETWEEN 1 AND 5)` constraint, at the cost of delete being a
multi-statement transaction instead of a 1-liner.

## Add-file behavior

Max 5 enforced at the application layer inside the insert transaction —
not a DB constraint, so a clean rejection error can be returned.

`SELECT COUNT(*) ... FOR UPDATE` on `bundle_files` does **not** actually
serialize this — it only locks rows that already exist and match, it does
nothing to block a concurrent transaction from inserting a *new* row. Two
simultaneous adds can both pass the count check and both insert, exceeding 5.
Correct pattern: lock the parent `bundles` row first, forcing concurrent
add-file transactions to queue on that lock.

```sql
BEGIN;
SELECT id FROM bundles WHERE id = $1 FOR UPDATE;      -- serializes concurrent adds
SELECT COUNT(*) FROM bundle_files WHERE bundle_id = $1;
-- if count < 5: INSERT INTO bundle_files (bundle_id, position, ...) VALUES ($1, count + 1, ...);
COMMIT;
```

Default name on creation: `untitled-{position}` (sequential), not a random
string — random strings are reserved for the bundle's `code` (needs to be
unguessable), a filename is just a label the user will rename anyway.

## Rename

Folded into the same PATCH as content edits conceptually, but since content
edits move to the OT path, rename remains the one direct-write use of
`PATCH /b/{code}/files/{file_id}`. Duplicate names allowed within a bundle
(no uniqueness constraint) — `position` is the real identifier, matching
Google Sheets' own tab-naming behavior.

Renaming can change the file's extension, which means the frontend must
re-resolve CM6 language mode on name change, not just on initial load.

## Live editing — OT, not plain save

Originally scoped as plain save / last-write-wins for simplicity. Reversed:
bundles need true multi-user live edit (n users editing the same file
simultaneously), reusing the OT system already built for single-file share
(20-file OT implementation, Redis-backed).

**Key design point: no new room architecture.** A bundle file is not a new
kind of room — it's the *same* kind of room the existing single-file share
already uses, just keyed differently.

- **Room key = `bundle_files.id`**, in place of `code_id` (the key used for
  a single shared snippet's room today). Same transform logic, same Redis
  room-state pattern, same websocket/broadcast mechanism — only the source
  of the key changes.
- **No bundle-level room.** Each of the 5 files is an independent room, live
  only while someone has that specific file open. A user on file 1 and
  another on file 3 never share a room. Switching tabs = leave room A,
  join room B — identical to navigating between two separate shared
  snippets today.
- **No relationship in Postgres.** Redis room state doesn't know or care
  what a "bundle" is — it's content-addressed by whatever key it's handed.
  No FK, no join table, no "this file has a room" column anywhere.

**Flush (persistence) triggers, in order:**
1. Periodic interval while the room is active (e.g. every 5–10s) — required
   so a crash or network drop mid-session doesn't lose everything since the
   last flush.
2. On last user leaving the room — final flush, Redis room state then
   discarded.
3. Optional courtesy flush on explicit tab-switch/navigate-away.

Flush target:
```sql
UPDATE bundle_files
SET content = $1, last_edited_by = $2, updated_at = now()
WHERE id = $3
```

**No manual save exists anywhere in this flow.** A user opens a bundle,
edits a file, and leaves — no save button, no `/save` call from the client.
The flush already wrote their changes to `bundle_files.content` before or
as they leave. If a save button is kept in the UI for familiarity, it's
cosmetic — a status indicator, not a functional trigger.