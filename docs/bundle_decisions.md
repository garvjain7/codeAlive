# Bundle Feature — Locked Design Decisions

Last updated: 2026-08-16

---

## 1. Auth & Access
- Bundles are **logged-in users only**. No anonymous creation, no anonymous access.
- Access model: one shareable link `/b/{code}` + login. No invite/ACL table.

---

## 2. Bundle Types — Strict Homogeneity
- A bundle is either **all text/code files** OR **all binary files**. Never mixed.
- `bundles.bundle_type` (`'text'` | `'binary'`) is set at creation from `validate_upload_file()`.
- When adding a file to an existing bundle, `validate_upload_file()` is run and `is_text`
  result must match `bundle_type`. Reject with `400` if type mismatch.
- Enforced at application layer (router), not DB trigger.

---

## 3. Schema — Two Separate File Tables (not one with nullable columns)

### Parent
- `bundles` — owner, code, bundle_type, permission, expiry, bundle-level password

### Text bundles
- `bundle_text_files` — stores `encoded_content` (gzip+base64, same as `user_snippets`)
- `bundle_text_file_access_control` — per-tab password lockout tracking

### Binary bundles
- `bundle_binary_files` — metadata only in PG; `file_id` TEXT = R2 object key (same pattern as `user_file_uploads.file_id`)
- `bundle_binary_file_access_control` — per-tab password lockout tracking

### Access control
- `bundle_access_control` — bundle-level password lockout tracking

### Primary keys
- All tables use `UUID PRIMARY KEY DEFAULT uuid_generate_v4()` — consistent with rest of DB.

---

## 4. Content Storage — Text Files
- `bundle_text_files.encoded_content` stores **gzip-compressed + base64-encoded** text.
  Named `encoded_content`, NOT `content`, to match `user_snippets.encoded_content`.
- Raw text NEVER persists to PG. OT engine in Redis always holds raw text.
- Cold read (seeding Redis): `decompress_code(encoded_content)` → raw text → Redis.
- Flush (write to PG): raw text from Redis → `compress_code()` → `encoded_content` in PG.

---

## 5. Real-Time Editing — OT Layer
- OT engine (Redis-based) is **reused as-is** from the room collaboration feature.
- The OT Redis layer and the bundle DB tables have **no relation** to each other.
- Bundle files do NOT use `rooms`, `room_participants`, `document_snapshots`, or
  `operation_log` tables. Those belong exclusively to the room collaboration feature.
- Each bundle text file is an independent OT session keyed in Redis by `bundle_file:{file_id}`.

---

## 6. Flush Trigger — Frontend Idle Detection
- Flush is **NOT** a server-side background timer.
- Flush is triggered by the **frontend**: 5-second debounce after last keystroke.
- Frontend calls `POST /b/{code}/files/{file_id}/flush` (HTTP, not WS message).
- Backend: read raw text from Redis for that key → `compress_code()` → write `encoded_content` to PG.
- On last user leaving (WS disconnect): final flush also triggered from WS disconnect handler.

---

## 7. Permission Model
- `admin_only` — only owner can edit content, rename files, add files, remove files.
  Non-owners can VIEW (read-only) — bundle is NOT blocked for them.
- `anyone` — any authenticated link-holder can edit content and rename files.
  Delete, add-file, permission-change stay owner-gated regardless.
- `get_bundle_by_code()` returns `can_edit` boolean — frontend uses this to set
  editor to `readOnly: true` and disable structural controls.

---

## 8. Password Protection
- Two levels: **bundle-level** (`bundles.is_password_protected`) and **per-tab level**
  (`bundle_text_files.is_password_protected` / `bundle_binary_files.is_password_protected`).
- Lockout pattern: same as `snippet_access_control` / `file_access_control` —
  3 failed attempts → 10-minute lockout, tracked per `(resource_id, user_id)`.
- Verify endpoints follow the same pattern as `POST /{code_id}/verify` in `api_snippets.py`.

---

## 9. Position & Tab Ordering
- Positions are contiguous integers 1..N (max 5).
- On delete: two-pass negative shift to avoid `UNIQUE(bundle_id, position)` collision:
  Pass 1: `SET position = -position WHERE position > $deleted_position`
  Pass 2: `SET position = -position - 1 WHERE position < 0`
- All within same transaction with parent bundle row locked (`SELECT ... FOR UPDATE`).

---

## 10. Binary Files — R2 Storage
- Binary file bytes stored in Cloudflare R2; `bundle_binary_files.file_id` = R2 object key.
- On delete: `client.delete_object(Key=file_id)` THEN `DELETE FROM bundle_binary_files`.
- Binary files are NOT OT-editable. WS endpoint returns `4003` if `bundle_type = 'binary'`.
- `download_count` tracked in `bundle_binary_files`, incremented on each download.

---

## 11. No Save Button
- For text bundles: no manual save. Flush is automatic (idle detection).
- If a save button exists in UI, it is cosmetic only (status indicator, not a write trigger).
