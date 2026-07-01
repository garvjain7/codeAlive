# CodeAlive File Upload & Sharing Feature — Implementation Plan

## Goal
Implement the new file-sharing feature in two separate paths:

1. Path A: import text-based files into the existing editor flow and share them through the current snippet save route.
2. Path B: upload binary files through a new standalone file-upload experience, store them in R2, and preview/download them through a dedicated viewer route.

This plan assumes the database schema is already in place and that the feature should follow the existing CodeAlive architecture and conventions.

---

## Implementation Principles
- Reuse existing snippet-sharing behavior wherever possible instead of creating parallel logic unnecessarily.
- Keep Path A fully client-side until the existing share/save flow is triggered.
- Keep Path B isolated from the editor flow; it should use its own UI, backend route, and storage handling.
- Reuse the existing custom-slug generation logic already used for snippet code IDs/custom slugs; do not introduce a new file-specific ID generator.
- Use the file ID directly as the R2 object key; do not add a separate storage-key column.
- Keep the viewer on its own route, separate from the editor and separate from the snippet share experience.
- Avoid introducing any new build tool, bundler workflow, or Node.js dependency; follow the existing plain HTML/CSS/JS + ESM frontend pattern.
- Use browser-native ES modules and CDN-based imports where needed, consistent with the current codebase.
- Validate aggressively on the client before any upload or save action occurs.
- Do not assume any hidden behavior; confirm route and UI integration points before implementation.

---

## Phase 1 — Backend Foundation
### Scope
Add the backend infrastructure needed for binary file support without changing the existing snippet pipeline.

### Tasks
- Locate and confirm the existing custom-slug / ID generation route used by snippet sharing before implementing any file-specific ID logic.
- Create a new file API router for upload, metadata storage, preview metadata lookup, and download requests.
- Add a small storage abstraction layer for R2/S3-compatible object storage.
- Add database access helpers for:
  - anonymous file uploads
  - user file uploads
  - file access control
- Ensure the backend uses the file ID directly as the R2 object key and does not invent a separate storage key.
- Choose the storage driver in a way that matches the existing async/sync pattern already used in core/mongodb.py and core/redis_client.py.

### Files likely to change
- api/file_router.py (new)
- core/r2_client.py (new)
- services/file_service.py (new)
- db/file_uploads.py (new)
- app.py (router registration if needed)

### Deliverable
A backend that can accept a binary upload, save metadata, store the raw file in R2, and serve it back through a controlled download route.

---

## Phase 2 — Path A: Editor Text Import
### Scope
Allow users to import supported text-based files into the existing editor without changing the current snippet save workflow.

### Tasks
- Add a separate import control inside the editor UI that is distinct from the binary upload UI.
- Read the selected file client-side using FileReader.
- Apply validation before injecting content:
  - extension allow-list
  - size limit
  - content sniff to reject suspicious binary content
- Replace the editor contents with the imported text using the existing CodeMirror document update mechanism.
- Optionally sync the editor language based on the file extension.
- Leave persistence unchanged; the existing save/share flow should still be used.

### Files likely to change
- static/editor-file-import.js (new)
- templates/index.html or the editor container UI
- static/editor.js if integration points are needed

### Deliverable
Users can inject supported text files into the editor and then continue using the existing share flow without any new save behavior.

---

## Phase 3 — Path B: Binary File Upload and Metadata Storage
### Scope
Create a dedicated binary-file sharing experience with its own UI and storage flow.

### Tasks
- Add a separate file upload interface that is not part of the editor.
- Enforce client-side validation for:
  - allowed file types
  - per-category size limits
  - rejected zip files
- Reuse the existing snippet custom-slug/ID flow for file IDs rather than creating a new generator.
- Upload the raw file bytes to R2 using the file ID as the object key.
- Save metadata to the proper database table depending on auth state:
  - anonymous upload -> anonymous file table
  - logged-in upload -> user file table
- Enforce the logged-in rule that title is mandatory for user_file_uploads and absent for anonymous uploads.
- Present the same share modal style and flow as the existing snippet share experience where appropriate.

### Files likely to change
- static/file-upload.js (new)
- api/file_router.py
- services/file_service.py
- db/file_uploads.py

### Deliverable
A working upload-to-share flow for supported binary files with stored metadata and object storage persistence.

---

## Phase 4 — Preview and Viewing Experience
### Scope
Render uploaded binary files inside CodeAlive’s own UI without using browser-native raw-file handling or external redirects.

### Tasks
- Add a dedicated viewer route or page flow for file shares, separate from the editor and separate from the snippet share experience.
- Render preview content based on file type:
  - images: img element
  - video: video element
  - pdf: pdf.js viewer
  - docx: client-side document preview
  - xlsx: client-side table rendering
- Keep the viewer separate from the code editor UI.
- Use backend-controlled download requests for all downloads.
- Ensure the download endpoint increments download_count for logged-in file uploads on every backend-proxied download.
- Keep the implementation compatible with the current no-build-step frontend setup and avoid any Node-based tooling.

### Files likely to change
- static/file-preview.js (new)
- static/css/file-viewer.css (new)
- templates or frontend route handling for shared file views
- api/file_router.py

### Deliverable
Users can open a shared file and preview it inside the site without being redirected to a raw object URL.

---

## Phase 5 — Access Control, Password Protection, and Expiry
### Scope
Bring the new file shares under the same security model as snippets where appropriate.

### Tasks
- Implement password protection for logged-in file shares.
- Implement access control against the finalized file_access_control table using the composite primary key (file_id, user_id).
- Apply the finalized lockout behavior: 3 failed attempts lock that pair for 5 minutes.
- Enforce expiry rules for logged-in file shares.
- Keep anonymous file shares simple and non-expiring, matching the pattern from anonymous snippets.
- Ensure download requests also enforce guard checks, not only the initial preview request.

### Files likely to change
- api/file_router.py
- db/file_uploads.py
- services/file_service.py

### Deliverable
File shares respect the same basic protections and access rules as the existing snippet system.

---

## Phase 6 — Testing and Verification
### Scope
Verify the feature end-to-end with realistic inputs and failure cases.

### Tasks
- Test supported text imports into the editor.
- Test rejected files and invalid MIME/extension combinations.
- Test binary uploads for each supported type.
- Test preview rendering for each previewable type.
- Test password-protected file access and lockout behavior.
- Test expiry behavior for logged-in files.
- Test download behavior and ensure backend-proxied access is used.

### Deliverable
A feature that behaves correctly for both happy paths and validation failures.

---

## Suggested Implementation Order
1. Confirm the existing snippet custom-slug / ID route and storage-driver pattern before writing any file-specific logic.
2. Backend routes and storage abstraction
3. Database access layer and metadata handling
4. Path A editor import UI
5. Path B binary upload UI and upload API
6. Preview/viewer implementation
7. Access control, password protection, expiry, and download_count handling
8. Testing and final polish

---

## Approval Gate
I will not start implementation until you approve this plan or request changes.
