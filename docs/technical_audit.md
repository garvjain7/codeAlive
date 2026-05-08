# CodeAlive: Technical Architecture & System Audit
**Classification:** Internal Engineering Reference  
**Status:** Active Production State

---

## 1. System Overview
CodeAlive is an asynchronous, API-driven web application designed for secure code snippet sharing, language detection, and collaborative workspaces. It operates on a multi-tier data architecture enforcing strict boundaries between anonymous public access and authenticated private management.

## 2. Technology Stack
**Backend Environment**
- **Framework:** FastAPI / ASGI (served via Uvicorn)
- **Runtime Assumptions:** Python 3.9+ async environment. Assumes single-thread per worker event loop.
- **Relational Database:** PostgreSQL (Neon) using `asyncpg` for non-blocking I/O.
- **NoSQL Database:** MongoDB Atlas using `pymongo` (Synchronous).
- **In-Memory Store:** Redis (`redis.asyncio`) for session state and fast lookups.
- **External Integrations:** Gmail SMTP via `smtplib`.

**Frontend Environment**
- **Architecture:** Vanilla JavaScript (ES6 modules) avoiding heavy SPA frameworks.
- **Editor:** CodeMirror 6 with custom Webpack/Rollup bundling.
- **DOM Management:** Direct DOM manipulation via isolated DOM map files (e.g., `workspace-dom.js`).

## 3. Architecture & Request Flow
The application follows a standard ASGI lifecycle:
1. **Ingress:** HTTP request is received by Uvicorn and passed to the FastAPI router.
2. **Middleware Interception:** `AuthMiddleware` intercepts the request, reads the `session_id` cookie, and queries Redis asynchronously.
3. **State Injection:** If authenticated, `user_id` is injected into `request.state.user_id` and the Redis TTL is refreshed (Rolling Session).
4. **Route Processing:** The specific route handler executes business logic. Heavy CPU operations (like language detection) are pushed to an `asyncio` ThreadPool. Fire-and-forget tasks (SMTP, Logging) are pushed to FastAPI `BackgroundTasks`.
5. **Egress:** JSON or HTML response is returned, and `BackgroundTasks` are flushed.

## 4. Authentication & Session Management
- **Strategy:** Stateful Session-based authentication. JWTs are *not* used.
- **Storage:** Sessions are stored in Redis as `session:{session_id}` -> `user_id`.
- **Rolling TTL:** The session TTL is exactly 7 days (`604800` seconds). The `AuthMiddleware` actively resets this TTL on every authenticated request (excluding `/static/` and `/auth/logout`), ensuring active users are never randomly logged out.
- **Cookie Security:** The `session_id` is delivered via `HttpOnly`, `Secure`, and `SameSite=lax` cookies.
- **Password Lifecycle:** Passwords are mathematically hashed via `bcrypt`. Reset links generate a 32-byte cryptographically secure token, hash it via SHA-256, and store the hash in PostgreSQL with a 20-minute expiry.

## 5. Data Storage & Schema Design
The application utilizes polyglot persistence to separate concerns:

**PostgreSQL (Core Relational Data via Connection Pool)**
- `users`: Tracks registered users (`user_id`, `username`, `email`, `password_hash`).
- `anonymous_snippets`: Stores stateless, ownerless snippets.
- `user_snippets`: Stores authenticated snippets with foreign key constraints, `is_password_protected` flags, `expires_at` timestamps, and `title`.
- `password_reset_tokens`: Stores hashed tokens to prevent DB leak exploitation.
- `snippet_access`: An audit log table mapping `user_id` to `code_id` for tracking who viewed protected snippets.

**MongoDB (Document Data)**
- `waitlist`: A simple collection tracking email signups.

**Data Consistency & Encoding**
- Snippet code is NOT stored as raw text. Before hitting the DB, it passes through `compress_code` which performs `gzip.compress()` followed by URL-safe Base64 encoding.

## 6. API Design & Endpoints
- **Design Pattern:** Hybrid REST-like API.
- **HTML Routing:** Routes like `/`, `/editor`, `/login`, `/workspace` return compiled Jinja2 templates.
- **API Routing:** Routes under `/api/` or specific actions like `/save` return strict JSON.
- **Idempotency:** Operations like "Joining Waitlist" check for existing entries and return custom 400 structures instead of crashing with 500s.

## 7. Security Mechanisms
- **CPU Exhaustion Prevention:** The `validate_code` function strictly enforces a 1MB byte-size limit AND a 1000-line limit *before* passing strings to the CPU-bound `gzip` function. This prevents single-line payload DoS attacks.
- **Access Control Boundaries:** Anonymous users can create snippets, but only authenticated users can specify titles, passwords, and expiration dates.
- **Snippet Protection:** Password-protected snippets require a successful verification POST request before the actual snippet payload is delivered.
- **XSS Prevention:** Code relies on CodeMirror's internal sanitization and avoids `innerHTML` injection of raw snippet data.

## 8. Performance Characteristics
- **Connection Pooling:** `asyncpg` utilizes a connection pool initialized on startup. However, the pool size is currently unbounded/implicitly defaulted.
- **Non-Blocking Network:** PostgreSQL and Redis calls are fully asynchronous, keeping the event loop unblocked.
- **Backgrounding:** SMTP email dispatches (`smtplib`) and logging functions (`safe_log`) are attached to FastAPI `BackgroundTasks`. This prevents network handshakes from artificially inflating API latency.
- **Thread Pooling:** The machine-learning/heuristic language detection is executed via `run_in_executor` to avoid halting the ASGI thread.

## 9. Error Handling Strategy
- **Backend:** Errors are raised using FastAPI's `HTTPException`, which standardizes the error response to `{ "detail": "Message" }`.
- **Frontend:** API requests via `fetch` explicitly check `!response.ok`. If failed, the frontend parses the JSON error and displays it via a non-blocking UI Toast mechanism (`showToast()`), explicitly avoiding thread-blocking `alert()` prompts.

## 10. Observability & Logging
- **Logging implementation:** A centralized `safe_log(msg, data)` function is used.
- **Execution:** Logging is strictly executed via `BackgroundTasks` so that slow disk writes or future external logging integrations (e.g., Datadog) do not impact user request times.
- **Coverage:** Logs capture user signups, failed/successful logins, and waitlist interactions.

## 11. Edge Cases & Hidden Behaviors
- **Timezone Mismatch / Drift Risk:** There is a known architectural drift between `api_snippets.py` (which calculates expiry via `datetime.utcnow()`) and `app.py` (which checks expiry via `datetime.now()`). If the production server is not strictly configured to UTC, this naive comparison will cause snippets to expire preemptively or far too late.
- **Module-Level Execution:** MongoDB indices are built at the module import level.

## 12. Known Limitations & Risks (Unresolved)
- **MongoDB Event Loop Blocking:** While Postgres and Redis are fully async, the application uses the synchronous `pymongo` library for the waitlist. Because this is not running in a BackgroundTask or thread pool, a heavy spike in waitlist traffic will freeze Uvicorn workers while waiting for DB ACKs.
- **Connection Scaling:** Uvicorn workers scale horizontally. The `asyncpg.create_pool()` does not define strict min/max connections. Under high auto-scaling events, workers may request more persistent connections than the Neon free/pooled tier permits, leading to `TooManyConnectionsError`.
- **No Rate Limiting:** The `/save` endpoint allows unrestricted, unauthenticated snippet creation, presenting a vector for storage exhaustion.
