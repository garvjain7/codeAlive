# File Sharing Architecture Plan

## Objective
Make file sharing follow the same architectural principles as snippet sharing in CodeAlive, while keeping the file experience distinct enough to support previews, downloads, and storage-backed content.

## Current Architectural Difference
The current file feature is moving toward a separate, storage-heavy flow that does not yet fully mirror the existing snippet architecture. The main differences are:

1. Snippets are centered around a single public share route and a simple render flow.
2. Files currently mix three concerns in one place:
   - storage access
   - access control and password protection
   - presentation/view rendering
3. The file system is more stateful because it depends on object storage, metadata, and per-file preview behavior.
4. The current implementation risks becoming a parallel feature with its own rules instead of a first-class CodeAlive feature.

## Architectural Goal
Create a file-sharing system that is still clearly separate from snippets, but uses the same core pattern:

- one canonical shareable record
- one public route for viewing
- backend-enforced permission and expiry rules
- browser-based rendering of the preview experience
- storage as the source of bytes, not as an ad-hoc side channel

## What to Fix

### 1. Separate routing from rendering
- Keep the public file route as /f/{file_id}.
- Keep the viewer page as the presentation layer.
- Avoid turning the view route into a storage utility or an overloaded backend endpoint.

### 2. Make the backend the source of truth
- The backend should own:
  - file existence
  - expiry
  - password protection
  - lockout logic
  - download access
- The browser should not decide access rules.

### 3. Keep storage logic isolated
- File bytes should live in R2.
- Metadata should live in the database.
- The file router should coordinate these two layers, not duplicate logic across the app.

### 4. Make preview rendering a presentation concern
- Preview behavior should be implemented in the viewer page and frontend JS.
- File content should be fetched through controlled routes, not embedded inline in the view layer.

### 5. Avoid feature drift
- Do not let file sharing grow into an independent architecture with duplicate auth, duplicate share logic, or duplicate state handling.
- Reuse the same patterns as snippets for:
  - route shape
  - public/private visibility
  - access checks
  - user-vs-anonymous behavior

## Implementation Plan

### Phase 1 — Normalize the structure
- Keep one canonical file model for metadata.
- Keep one canonical public route for sharing: /f/{file_id}.
- Ensure the view page and download route both derive from the same backend decision layer.

### Phase 2 — Move access logic to a single flow
- Centralize password, expiry, and lockout checks in one shared function or helper.
- Make both preview and download use that same guard path.
- Avoid repeating access-control logic in multiple route handlers.

### Phase 3 — Keep storage and presentation separated
- The storage layer should only save and read bytes.
- The viewer should only render and present the fetched file.
- The router should coordinate these responsibilities.

### Phase 4 — Align the frontend with the architecture
- The frontend should render previews using the same pattern as CodeAlive’s editor experience:
  - lightweight UI shell
  - browser-driven rendering
  - no hidden state duplication
- The public file page should feel like a native CodeAlive page, not a generic upload viewer.

### Phase 5 — Keep the design consistent with CodeAlive
- Reuse the same visual language as the existing editor and home page.
- Keep action buttons and navigation consistent with the current product pattern.
- Preserve the same feel of “share, view, download” that snippets already provide.

## Expected Outcome
After this plan, file sharing will be architecturally consistent with CodeAlive:

- the backend remains the source of truth
- the public route is clean and predictable
- access control is centralized
- storage is isolated
- rendering is presentation-only
- the feature feels like part of the product rather than a separate subsystem
