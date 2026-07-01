# Production-Grade Architecture: CodeAlive Collaboration Frontend

This document defines the high-level architecture for the real-time collaboration system. It prioritizes **Synchronization State Isolation** and **Connection Lifecycle Management** to ensure stability across high-concurrency and unstable network conditions.

---

## 1. Architectural Layers (Separation of Concerns)

To avoid a "god-object" and ensure maintainability, the frontend is divided into five distinct layers:

### A. Transport Layer (`transport.js`)
**Responsibility**: Raw communication.
- Manages the `WebSocket` instance.
- Implements **Exponential Backoff** for reconnections.
- Handles Heartbeats (Pings) to keep the connection alive.
- Does NOT know about CodeMirror or OT math. It only sends/receives raw JSON.

### B. Synchronization Engine (`sync_engine.js`)
**Responsibility**: The "Brain" of the collaboration.
- **State Model**:
    - `server_revision`: The last revision confirmed by the server.
    - `inflight_op`: The operation currently awaiting an `ACK`.
    - `pending_queue`: Buffer of local edits made while an op is in-flight.
- **Logic**: Performs the actual Operational Transformation (OT) math.
- Editor-agnostic: It works with strings and offsets, not DOM elements.

### C. Editor Adapter (`codemirror_adapter.js`)
**Responsibility**: The "Translator."
- Listens to CodeMirror `Transactions`.
- Converts CM6 `ChangeSets` into our internal `Op` format.
- Applies remote operations back to the CodeMirror view using `view.dispatch`.
- Manages **Remote Cursors** and selections via CodeMirror Decorations.

### D. Presence Manager (`presence.js`)
**Responsibility**: Awareness.
- Tracks active users, their cursor positions, and selection ranges.
- Throttles cursor updates (~50ms) to reduce network noise.
- Presence is "Lossy": If a cursor update is dropped, it doesn't break the document state.

### E. Room State Store (`room_store.js`)
**Responsibility**: Business Logic.
- Stores metadata: Room Title, Host ID, User Role (Host/Participant).
- Manages UI state: `isLocked`, `isMuted`, `isApprovalPending`.

---

## 2. Connection Lifecycle (State Machine)

The client must always be in exactly one of these states. UI components should react to these states (e.g., showing a "Reconnecting..." banner).

| State | Description | UI Behavior |
| :--- | :--- | :--- |
| `DISCONNECTED` | Initial state or manual close. | Overlay: "Disconnected" |
| `CONNECTING` | WebSocket opening handshake. | Spinner: "Connecting..." |
| `SYNCING` | Loading initial document snapshot. | Spinner: "Loading Workshop..." |
| `READY` | Fully synchronized and interactive. | Normal Editor UI |
| `RECONNECTING` | Socket lost, attempting to restore. | Banner: "Connection Lost... retrying" |
| `RESYNCING` | Catching up after a long disconnect. | Overlay: "Catching up..." |

---

## 3. The Synchronization Loop (OT Model)

We follow the **Single In-Flight Op** pattern:
1.  **Local Edit**: User types -> Add to `pending_queue` -> Apply to local view.
2.  **Send**: If `inflight_op` is null, move first item from `pending_queue` to `inflight_op` and send to server.
3.  **Receive ACK**: Server returns `OP_ACK` -> Clear `inflight_op` -> Increment `server_revision` -> Send next pending.
4.  **Receive Broadcast**: Server sends `OP_BROADCAST` from another user -> **Rebase** `inflight_op` and `pending_queue` against the incoming op -> Update local view.

---

## 4. Reconnection & Resync Flow

If the connection is lost:
1.  **Transition** to `RECONNECTING`.
2.  **Editor State**: Set to `readOnly: true` to prevent unmanageable fork states (Senior decision: avoid offline-edit complexity).
3.  **On Reconnect**:
    - If `reconnect_sid` is valid: Server sends missed ops -> Client applies them -> Transition to `READY`.
    - If `RESYNC_REQUIRED` (History lost): 
        - Frontend pauses everything.
        - Fetches a fresh full snapshot via HTTP/WS.
        - Reinitializes the editor with the new content.
        - Transition to `READY`.

---

## 5. Performance Optimization

- **Decoration Churn**: Remote cursors will be rendered using a "Persistent Decoration" strategy to avoid re-rendering the entire editor on every cursor move.
- **Operational Batching**: Consecutive character inserts will be collapsed into a single multi-character "Insert" operation before being sent to the server.
- **Undo History**: We use a `TransactionFilter` to ensure that Ctrl+Z ONLY reverts local user changes, never remote operations.

---

## 6. Security & Permissions

- **Authoritative Server**: The server is the final arbiter of truth. If a client tries to apply an operation it isn't authorized for (e.g., muted user), the server will terminate the connection.
- **Handshake**: Authenticated via `session_id` query parameter.
