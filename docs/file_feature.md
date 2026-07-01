# CodeAlive — File Upload & Sharing Feature: Planning Document

## 1. Feature Summary

CodeAlive currently supports sharing **code/text snippets** (editor content) via a
generated link, with anonymous and logged-in flows, optional password protection,
and expiry (logged-in only). This feature extends sharing to **files** — both
text-based files (which route into the existing CodeMirror editor) and binary
files (which get a separate, dedicated viewer interface).

Two distinct upload paths exist. They are not the same feature wearing different
clothes — they hit different storage backends, different tables, and different UI.

---

## 2. The Two Upload Paths

### 2.1 Path A — Editor Text Extraction (existing snippet flow, extended)

**Trigger:** An "upload" control inside the editor, separate from the binary
file-upload UI.

**Allowed inputs:** `.txt`, `.md`, `.json`, `.csv`, plus any of the ~25–30
programming language file extensions already recognized by CodeMirror's
`@codemirror/language-data` package (the same list `LanguageDescription.matchLanguageName`
already resolves against in `editor.js`).

**Mechanism:**
1. Client-side only, no server round-trip at upload time.
2. `FileReader.readAsText()` reads the selected file as UTF-8.
3. **Client-side validation before injecting into the editor:**
   - Extension must match the allowed list.
   - A content sniff (reject if the read result contains null bytes / invalid
     UTF-8 sequences) as a safety net against a mislabeled binary file (e.g. a
     `.png` renamed to `.txt`).
   - On failure: explicit rejection message shown to the user — never silently
     truncate or inject garbled content.
4. On success: `view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: extractedText } })`
   — a full-document replace. CodeMirror owns document state directly (confirmed
   from `editor.js` — this is architecture (a), not a mirrored-textarea setup),
   so this is a single dispatch, nothing else required.
5. Optionally auto-set the language Compartment via `setLanguage()` based on
   the uploaded file's extension, matching normal editor behavior.
6. **No save happens on upload.** Exactly like manually typed content, nothing
   is persisted until the user clicks Generate Link / Share. At that point the
   **existing `/save` route runs unmodified** — it already performs encode +
   compress + write to `anonymous_snippets` or `user_snippets` depending on
   auth state. This upload path is purely a text-injection convenience in
   front of a save flow that already exists and already works.

**Size limit:** 1MB (client-enforced before `readAsText()` even runs, to avoid
loading huge files into memory pointlessly).

**Storage:** Same as manually-typed snippets — `anonymous_snippets` /
`user_snippets`, no new table involved for this path.

---

### 2.2 Path B — Binary File Upload (new feature, new table, new storage)

**Trigger:** A separate upload interface, not part of the editor at all.

**Allowed types (11 total, confirmed, zip explicitly excluded):**

| Category | Types | Size limit |
|---|---|---|
| Image | jpg/jpeg, png, svg | 500 KB |
| Document | pdf, docx, xlsx | 500 KB |
| Video | mp4 | 5 MB |

**Client-side validation before upload attempt:**
- Extension + MIME type check against the allowed list.
- Size check against the per-category limit above.
- Explicit rejection message on failure (never silent).

**Storage backend: Cloudflare R2** (S3-compatible object storage).
- Free tier: 10 GB total storage, 1,000,000 Class A (write) ops/month,
  10,000,000 Class B (read) ops/month, **zero egress fees**, no expiry on the
  free tier itself (unlike AWS S3's 12-month-only free tier).
- Requires a Cloudflare account with a card on file to enable R2, but no
  charges occur while under free-tier limits.
- Files are stored as **raw binary** — no base64 encoding, no compression
  step. This is a deliberate divergence from the Postgres snippet pipeline:
  - Encoding (base64) exists in the snippet pipeline because binary-adjacent
    content needs to survive a text column. R2 accepts raw binary directly via
    `PUT`, so encoding would only inflate size (~33%) for no benefit.
  - Compression is skipped because jpg/png/mp4/docx/xlsx are already
    internally compressed formats — re-compressing yields near-zero savings.
    svg is the one exception (plain XML, compresses well), and if desired
    later this is a one-line `Content-Encoding: gzip` addition, not a system
    requirement — **not implemented in this pass.**
- **`file_id` doubles as the R2 object key.** No separate key column. `file_id`
  is generated using the **same slug-generation logic that already exists for
  snippet `code_id`** (random generation, with the existing custom-slug
  capability available at share time) — this route is reused as-is, not
  reimplemented.

**Preview:** Rendered entirely inside CodeAlive's own UI. No browser-native
viewer, no redirect to a raw R2 URL, no OS handoff.

| Type | Preview method |
|---|---|
| jpg/jpeg, png, svg | `<img>` |
| mp4 | `<video>` |
| pdf | `pdf.js`, rendered inside a CodeAlive-styled viewer |
| docx | `mammoth.js` or `docx-preview` (client-side, no server conversion needed) |
| xlsx | `SheetJS` — parsed client-side, rendered as an HTML table |

All of the above are genuinely previewable — none require server-side
conversion (e.g. no LibreOffice headless step). This viewer is a new, separate
interface from the code editor; uploaded binary files are never shown inside
CodeMirror.

**Download:** Always proxied through the CodeAlive backend — fetched from R2
server-side and streamed to the client with `Content-Disposition: attachment`.
Never a direct/signed R2 URL handed to the client. This also ensures
password/expiry/lockout checks run on every single download request, not just
on first preview load.

**Share modal:** Identical component/flow to the existing snippet share modal
— same custom-slug support, same password-protection toggle, same behavior
for anonymous vs logged-in users.

---

## 3. Database Schema (PostgreSQL) — Final

Mirrors the existing `anonymous_snippets` / `user_snippets` split exactly,
rather than a single nullable-owner table — this preserves the same
constraint logic already proven in the snippet tables (e.g. anonymous files
never expire, exactly like anonymous snippets; logged-in files require a
title, exactly parallel to how logged-in snippets support one).

```sql
CREATE TABLE "anonymous_file_uploads" (
    "id" uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    "file_id" text NOT NULL CONSTRAINT "anonymous_file_uploads_file_id_key" UNIQUE,
    "original_filename" text NOT NULL,
    "file_type" text NOT NULL,          -- pdf | docx | xlsx | jpeg | png | svg | mp4
    "file_size_bytes" integer NOT NULL,
    "created_at" timestamp DEFAULT now()
);

CREATE TABLE "user_file_uploads" (
    "id" uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    "file_id" text NOT NULL CONSTRAINT "user_file_uploads_file_id_key" UNIQUE,
    "owner_id" uuid,
    "title" text NOT NULL,              -- mandatory for logged-in shares
    "original_filename" text NOT NULL,
    "file_type" text NOT NULL,
    "file_size_bytes" integer NOT NULL,
    "is_password_protected" boolean DEFAULT false,
    "password_hash" text,
    "expires_at" timestamp NOT NULL,
    "download_count" integer DEFAULT 0, -- logged-in files only
    "created_at" timestamp DEFAULT now(),
    CONSTRAINT "chk_file_expiry_future" CHECK ((expires_at > created_at)),
    CONSTRAINT "chk_file_password_logic" CHECK (
        (((is_password_protected = false) AND (password_hash IS NULL))
        OR ((is_password_protected = true) AND (password_hash IS NOT NULL)))
    )
);

CREATE TABLE "file_access_control" (
    "file_id" uuid,
    "user_id" uuid,
    "failed_attempts" integer DEFAULT 0,
    "last_failed_at" timestamp,
    "locked_until" timestamp,
    "first_success_at" timestamp,
    CONSTRAINT "file_access_control_pkey" PRIMARY KEY("file_id","user_id")
);

CREATE UNIQUE INDEX "idx_anon_file_id" ON "anonymous_file_uploads" ("file_id");
CREATE INDEX "idx_user_file_expiry" ON "user_file_uploads" ("expires_at");
CREATE INDEX "idx_user_file_owner" ON "user_file_uploads" ("owner_id");
CREATE INDEX "idx_file_access_file" ON "file_access_control" ("file_id");
CREATE INDEX "idx_file_access_user" ON "file_access_control" ("user_id");

ALTER TABLE "user_file_uploads" ADD CONSTRAINT "user_file_uploads_owner_id_fkey"
    FOREIGN KEY ("owner_id") REFERENCES "users"("user_id") ON DELETE CASCADE;
ALTER TABLE "file_access_control" ADD CONSTRAINT "file_access_control_file_id_fkey"
    FOREIGN KEY ("file_id") REFERENCES "user_file_uploads"("id") ON DELETE CASCADE;
ALTER TABLE "file_access_control" ADD CONSTRAINT "file_access_control_user_id_fkey"
    FOREIGN KEY ("user_id") REFERENCES "users"("user_id") ON DELETE CASCADE;
```

**Lockout behavior:** 3 failed password attempts on a `user_file_uploads` row
locks that specific `(file_id, user_id)` pair for 5 minutes — identical
mechanism to `snippet_access_control`, just against the new file table.
Anonymous file access has no lockout (mirrors anonymous snippets having no
access-control entry at all).

---

## 4. New Project Structure

Following the existing flat, token-conscious layout (`api/`, `core/`,
`services/`, `db/`, `static/`) rather than introducing a new top-level
convention:

```
api/
├── file_router.py          # NEW — upload, share, preview-data, download endpoints

core/
├── r2_client.py             # NEW — R2 (S3-compatible) client init, presign-free
                              #        (backend always proxies, no client-side
                              #        signed URLs per the download rule)

services/
├── file_service.py          # NEW — validation (type/size), R2 put/get/delete,
                              #        file_id generation (reuses existing
                              #        slug-generation logic from snippets)

db/
├── file_uploads.py          # NEW — queries against anonymous_file_uploads /
                              #        user_file_uploads / file_access_control
                              #        (parallel to db/snippets.py and
                              #        db/access_control.py)

static/
├── file-upload.js           # NEW — binary file upload UI (separate from editor)
├── file-preview.js          # NEW — preview rendering dispatch by file_type
│                             #        (img/video native; pdf.js, mammoth/docx-preview,
│                             #        SheetJS for the rest)
├── editor-file-import.js    # NEW — Path A: FileReader → validation → CodeMirror
│                             #        dispatch (separate from file-upload.js;
│                             #        this one never touches R2)
├── css/
│   └── file-viewer.css      # NEW — styling for the standalone binary-file viewer UI
```

`requirements.txt` gains an R2/S3 client (e.g. `boto3` configured against R2's
S3-compatible endpoint, or `aioboto3` if the rest of the FastAPI stack is
async — matching whichever pattern `mongodb.py`/`redis_client.py` already use
in `core/`).

Frontend gains, per `docs/CodeMirror_Migration_Audit.md`'s existing ESM-only,
no-build-step convention: `pdf.js`, `mammoth.js` (or `docx-preview`), and
`SheetJS`, all loaded the same way CodeMirror packages are — via `esm.sh` or
an equivalent CDN import, no bundler introduced.

---

## 5. Workflow Diagrams (textual)

### Path A — Editor text import
```
User selects file (upload button IN editor)
  → FileReader.readAsText()
  → extension + content-sniff validation
      → fail: show rejection message, stop
      → pass: dispatch full-doc replace into CodeMirror
  → user edits normally / language auto-detected
  → user clicks Generate Link / Share
      → EXISTING /save route runs unchanged
      → encode + compress + write to anonymous_snippets or user_snippets
```

### Path B — Binary file upload
```
User selects file (separate file-upload UI, not editor)
  → client validates type (11 allowed, zip excluded) + size (per category)
      → fail: show rejection message, stop
      → pass: continue
  → generate file_id (same logic as snippet code_id/custom slug)
  → upload raw binary to R2 under key = file_id
  → write metadata row:
      - anonymous_file_uploads (if not logged in) — no title, no expiry
      - user_file_uploads (if logged in) — title mandatory, expiry mandatory,
        optional password
  → share modal shown (identical component to snippet share modal)
      → custom slug option available (reuses existing snippet slug logic)
      → password toggle available (logged-in only, matches user_snippets rule)

Visiting share link:
  → lookup file_id in appropriate table
  → if password-protected: check file_access_control lockout state first
      → locked: reject with wait message
      → 3rd consecutive failure: lock (file_id, user_id) for 5 minutes
      → correct password: proceed, reset failed_attempts
  → if expired (user_file_uploads only): reject
  → fetch binary from R2 via backend (never a direct/signed URL to client)
  → render preview in CodeAlive UI per file_type dispatch table (Section 2.2)
  → download button: also proxies through backend, re-checks password/expiry/
    lockout every time, increments download_count (user_file_uploads only)
```

---

## 6. Explicitly Out of Scope for This Feature
- Rooms / real-time collaboration (`ot_collab/`, `static/collab/`) — untouched.
- Zip files — excluded entirely, not previewable, not uploadable.
- Server-side document conversion (LibreOffice etc.) — not needed; all 5
  previewable-but-non-native types (pdf, docx, xlsx + the 2 native image/video
  ones) are handled client-side.
- Compression/encoding of R2-stored binaries — deliberately skipped except as
  a possible future one-line addition for svg only.
- Workspace as a dedicated table — it remains a query (`WHERE owner_id = ?`)
  against `user_snippets` and, now, `user_file_uploads`; no new workspace
  entity introduced.

---

## 7. Open Items to Confirm Before/During Implementation
- Exact custom-slug generation function location (confirmed to exist, not yet
  viewed in this conversation) — reuse verbatim once located, do not
  reimplement independently.
- Exact `/save` route file location, to confirm the encode/compress order
  (base64 → gzip, or gzip → base64) before writing anything that touches
  `encoded_content` for the Path A flow (though Path A itself calls this route
  unmodified, so this mainly matters if any file-type-aware logic needs to be
  added to that route later).
- Confirm whether `boto3`/`aioboto3` (sync vs async) matches the rest of the
  FastAPI service's DB client pattern before adding it to `requirements.txt`.