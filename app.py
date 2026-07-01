from fastapi import FastAPI, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import asyncio
import json
import re
import os
import uvicorn

from core.utils import validate_code, compress_code, generate_id
from services.language_detector import detect_language
from api.image_router import router as image_router
from api.api_snippets import router as api_snippets_router, resolve_code_id
from core.auth_middleware import AuthMiddleware
from db.snippets import create_anonymous, get_snippet_by_code_id, create_user_snippet
from db.users import get_user_by_id
from datetime import datetime, timedelta
import uuid

from api.profile_router import router as profile_router
from api.workspace_router import router as workspace_router
from ot_collab.ws_router import router as collab_ws_router
from api.collab_router import router as collab_http_router
from api.auth_router import router as auth_router
from api.file_router import router as file_router
from ot_collab.grace_sweeper import start_grace_sweeper
# from services.mailer import send_waitlist_email
from services.mail_service_v2 import send_waitlist_email
from core.mongodb import waitlist_collection
from dotenv import load_dotenv
import db.connection as db_conn

load_dotenv()

from contextlib import asynccontextmanager

async def neon_keepalive_loop():
    """Background task to keep Neon DB alive by querying every 4 minutes."""
    import os
    from datetime import datetime
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neon_keepalive.log")
    while True:
        await asyncio.sleep(240)
        try:
            if db_conn.pool:
                async with db_conn.pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                with open(log_file, "a") as f:
                    f.write(f"[{datetime.utcnow().isoformat()}] Neon DB keepalive ping sent successfully.\n")
        except Exception as e:
            with open(log_file, "a") as f:
                f.write(f"[{datetime.utcnow().isoformat()}] Neon DB keepalive ping FAILED: {e}\n")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to PostgreSQL
    await db_conn.connect_db()
    
    # Start Neon DB keepalive loop
    keepalive_task = asyncio.create_task(neon_keepalive_loop())
    
    # Start Collaboration Grace Sweeper (scans for host timeouts)
    sweeper_task = asyncio.create_task(start_grace_sweeper())
    
    yield
    
    # Shutdown: Cancel background tasks
    keepalive_task.cancel()
    sweeper_task.cancel()
    
    try:
        await asyncio.gather(keepalive_task, sweeper_task, return_exceptions=True)
    except Exception:
        pass
        
    # Shutdown: Close pool
    await db_conn.close_db()

app = FastAPI(lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.include_router(image_router)
app.include_router(api_snippets_router)
app.include_router(profile_router)
app.include_router(workspace_router)
app.include_router(collab_http_router)
app.include_router(collab_ws_router)
app.include_router(auth_router)
app.include_router(file_router)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)


# ── Highlights sanitiser ──────────────────────────────────────────────────────
# Expected format: "L6-L14,L32-L49" (no leading '#').
_HIGHLIGHTS_RE = re.compile(r"^L\d+(-L\d+)?(,L\d+(-L\d+)?)*$", re.IGNORECASE)

# Reserved path names that must never be treated as snippet code_ids
_RESERVED = frozenset({"editor", "waitlist", "static", "s", "new", "robots.txt", "sitemap.xml", "login", "signup", "reset-password"})
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def sanitise_highlights(raw: str) -> str:
    """Return a valid highlights string, or empty string if invalid."""
    if not raw:
        return ""
    raw = raw.strip()
    if len(raw) > 200:
        return ""
    if not _HIGHLIGHTS_RE.match(raw):
        return ""
    return raw


def _parse_stored(stored: str) -> tuple[str, str, str]:
    """
    Parse a Redis-stored snippet value into (encoded, language, highlights).

    Handles all three historical formats:
      encoded/language/highlights   (current)
      encoded/language              (older)
      encoded                       (legacy, no language)
    """
    parts = stored.rsplit("/", 2)

    if len(parts) == 3:
        encoded, language, highlights = parts
    elif len(parts) == 2:
        encoded, language = parts
        highlights = ""
    else:
        encoded    = stored
        language   = "text"
        highlights = ""

    if not language or len(language) > 30:
        language = "text"

    return encoded, language, sanitise_highlights(highlights)


# ── Request model ─────────────────────────────────────────────────────────────

class DetectRequest(BaseModel):
    code: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Marketing homepage."""
    user_id = getattr(request.state, "user_id", None)
    user_email = None
    if user_id:
        async with db_conn.pool.acquire() as conn:
            user = await get_user_by_id(conn, uuid.UUID(user_id))
            if user:
                user_email = user["email"]
    return templates.TemplateResponse("home.html", {"request": request, "user_id": user_id, "user_email": user_email})


@app.get("/editor", response_class=HTMLResponse)
async def editor(request: Request):
    """Fresh editor — no snippet loaded."""
    user_id = getattr(request.state, "user_id", None)
    user_email = None
    if user_id:
        async with db_conn.pool.acquire() as conn:
            user = await get_user_by_id(conn, uuid.UUID(user_id))
            if user:
                user_email = user["email"]
    return templates.TemplateResponse(
        "index.html",
        {
            "request":    request,
            "encoded":    "",
            "language":   "text",
            "highlights": "",
            "user_id":    user_id,
            "user_email": user_email
        },
    )


@app.get("/workspace", response_class=HTMLResponse)
async def workspace_page(request: Request):
    """User workspace (snippets list). Strictly needs login."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return RedirectResponse(url="/login?next=/workspace")
    
    user_email = None
    async with db_conn.pool.acquire() as conn:
        user = await get_user_by_id(conn, uuid.UUID(user_id))
        if user:
            user_email = user["email"]
            
    return templates.TemplateResponse("workspace.html", {"request": request, "user_id": user_id, "user_email": user_email})


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """User profile page. Strictly needs login."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return RedirectResponse(url="/login?next=/profile")
    return templates.TemplateResponse("profile.html", {"request": request, "user_id": user_id})


@app.get("/new")
async def new_snippet():
    """/new → redirect to /editor. Common convention, nice to have."""
    return RedirectResponse(url="/editor", status_code=302)


@app.get("/waitlist", response_class=HTMLResponse)
async def waitlist_page(request: Request):
    """Waitlist landing page."""
    return templates.TemplateResponse("waitlist.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Signup page."""
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    """Reset Password page."""
    return templates.TemplateResponse("reset-password.html", {"request": request})


@app.get("/robots.txt")
async def serve_robots_txt():
    """Serve robots.txt from root."""
    return FileResponse(os.path.join(BASE_DIR, "robots.txt"))


@app.get("/sitemap.xml")
async def serve_sitemap_xml():
    """Serve sitemap.xml from root."""
    return FileResponse(os.path.join(BASE_DIR, "sitemap.xml"))


# @app.post("/waitlist")
# async def waitlist_join(email: str = Form(...), background_tasks: BackgroundTasks = None):
#     """
#     Accept an email address for the collaboration rooms waitlist.

#     Validation
#     ----------
#     - Basic format check (must contain @, domain, TLD)
#     - Duplicate guard — silently succeeds if already on list
#       (avoids leaking whether an email is registered)

#     Storage
#     -------
#     Temporarily written to waitlist.json on disk.
#     Replace _load_waitlist() / _save_waitlist() with a PostgreSQL
#     INSERT when the DB is wired in — the route itself stays identical.
#     """
#     email = email.strip().lower()

#     if not email or not _EMAIL_RE.match(email):
#         raise HTTPException(400, "Invalid email address")

#     loop = asyncio.get_running_loop()

#     # 1. Check if already exists in MongoDB (Offload to thread pool to prevent blocking)
#     existing = await loop.run_in_executor(None, lambda: waitlist_collection.find_one({"email": email}))
#     if existing:
#         raise HTTPException(400, "Email is already added")

#     # 2. Insert into MongoDB (Offload to thread pool to prevent blocking)
#     import datetime
#     payload = {
#         "email":      email,
#         "joined_at":  datetime.datetime.utcnow().isoformat(),
#     }
#     await loop.run_in_executor(None, lambda: waitlist_collection.insert_one(payload))

#     # 3. Send confirmation email
#     if background_tasks is not None:
#         background_tasks.add_task(send_waitlist_email, email)
#     else:
#         send_waitlist_email(email)

#     from core.utils import safe_log
#     if background_tasks is not None:
#         background_tasks.add_task(safe_log, "User joined waitlist", {"email": email})
#     else:
#         safe_log("User joined waitlist", {"email": email})

#     return JSONResponse({"ok": True, "message": "Email sent successfully"})

# import at top of main.py
# from services.mail_service_v2 import send_waitlist_email, send_reset_email

@app.post("/waitlist")
async def waitlist_join(email: str = Form(...), background_tasks: BackgroundTasks = None):
    # V2 — mail now goes via mail microservice on Fly.io
    email = email.strip().lower()

    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(400, "Invalid email address")

    loop = asyncio.get_running_loop()

    existing = await loop.run_in_executor(None, lambda: waitlist_collection.find_one({"email": email}))
    if existing:
        raise HTTPException(400, "Email is already added")

    import datetime
    payload = {
        "email":     email,
        "joined_at": datetime.datetime.utcnow().isoformat(),
    }
    await loop.run_in_executor(None, lambda: waitlist_collection.insert_one(payload))

    if background_tasks is not None:
        background_tasks.add_task(send_waitlist_email, email)
    else:
        send_waitlist_email(email)

    from core.utils import safe_log
    if background_tasks is not None:
        background_tasks.add_task(safe_log, "User joined waitlist", {"email": email})
    else:
        safe_log("User joined waitlist", {"email": email})

    return JSONResponse({"ok": True, "message": "Email sent successfully"})

@app.post("/detect-language")
async def detect_language_endpoint(body: DetectRequest):
    """
    Async language detection.

    Runs detect_language() in a thread-pool executor so it never blocks
    the FastAPI event loop.

    No try/except here — detect_language() has its own internal guard and
    always returns a string. If the executor itself fails for some unexpected
    reason FastAPI will return a 500, which triggerDetection() on the frontend
    handles correctly by calling setFailed().
    """
    loop     = asyncio.get_running_loop()
    language = await loop.run_in_executor(None, detect_language, body.code)
    return {"language": language}


@app.post("/save")
async def save(
    request: Request,
    code: str        = Form(...),
    language: str    = Form("text"),
    highlights: str  = Form(""),
    custom_code: str = Form(None),
    password: str    = Form(None),
    expiry: int      = Form(30),
    title: str       = Form(None)
):
    """
    Save a snippet to PostgreSQL and return its shareable URL.
    Maintained for backward compatibility with frontend actions.js.
    """
    validate_code(code)
    
    language = language.strip().lower() if language else "text"
    if not language or len(language) > 30:
        language = "text"
        
    highlights = sanitise_highlights(highlights)
    encoded = compress_code(code)
    
    user_id = getattr(request.state, "user_id", None)
    
    if user_id and not title:
        raise HTTPException(400, "Title is mandatory for registered users")
    
    async with db_conn.pool.acquire() as conn:
        code_id = await resolve_code_id(conn, custom_code)
        
        if user_id:
            # Default to 1 year expiration for now to satisfy NOT NULL constraint
            # Actually, user wants custom expiry
            if expiry < 1 or expiry > 90:
                expiry = 30
            
            expires_at = datetime.now() + timedelta(days=expiry)
            
            pwd_hash = None
            if password:
                import bcrypt
                salt = bcrypt.gensalt()
                pwd_hash = bcrypt.hashpw(password.encode(), salt).decode()
            
            await create_user_snippet(
                conn,
                code_id=code_id,
                owner_id=uuid.UUID(user_id),
                encoded_content=encoded,
                language=language,
                highlights=highlights,
                password_hash=pwd_hash,
                expires_at=expires_at,
                title=title
            )
        else:
            # Save as anonymous snippet
            await create_anonymous(
                conn,
                code_id=code_id,
                encoded_content=encoded,
                language=language,
                highlights=highlights
            )
        
        return {"url": f"/s/{code_id}"}


@app.get("/s/{code_id}", response_class=HTMLResponse)
async def view_snippet(request: Request, code_id: str):
    """
    Serve a shared snippet with access control and password protection.
    """
    user_id = getattr(request.state, "user_id", None)
    user_email = None

    async with db_conn.pool.acquire() as conn:
        if user_id:
            user = await get_user_by_id(conn, uuid.UUID(user_id))
            if user:
                user_email = user["email"]

        snippet = await get_snippet_by_code_id(conn, code_id)
        if not snippet:
            raise HTTPException(404, "Snippet not found")
        
        # Check if it's a user snippet (REQUIRES LOGIN)
        if snippet["type"] == "user":
            # If not logged in, redirect to login page for ANY user snippet
            if not user_id:
                return RedirectResponse(url=f"/login?next={request.url.path}")

            # Check if it has expired
            if snippet["expires_at"] < datetime.utcnow():
                raise HTTPException(410, "Snippet has expired")
            
            if snippet["is_password_protected"]:
                # MANDATORY: If protected, always show the password prompt on load.
                # This applies to EVERYONE, including the owner.
                return templates.TemplateResponse("index.html", {
                    "request": request,
                    "is_protected": True,
                    "code_id": code_id,
                    "encoded": "",  # NO CONTENT
                    "language": snippet["language"],
                    "highlights": snippet["highlights"],
                    "title": snippet["title"] or "Protected Snippet",
                    "user_id": user_id,
                    "user_email": user_email
                })
            
        return templates.TemplateResponse(
            "index.html",
            {
                "request":    request,
                "encoded":    snippet["encoded_content"],
                "language":   snippet["language"],
                "highlights": snippet["highlights"],
                "user_id":    user_id,
                "user_email": user_email,
                "is_protected": False
            },
        )


@app.get("/{code_id}", response_class=HTMLResponse)
async def legacy_snippet(code_id: str):
    """
    Legacy route — kept for backward compatibility with old shared links.
    """
    if code_id in _RESERVED:
        raise HTTPException(404, "Not found")

    async with db_conn.pool.acquire() as conn:
        snippet = await get_snippet_by_code_id(conn, code_id)
        if not snippet:
            raise HTTPException(404, "Snippet not found")

        return RedirectResponse(url=f"/s/{code_id}", status_code=301)


@app.get("/neon-logs", response_class=HTMLResponse)
async def get_neon_logs():
    return """
    <html>
        <body>
            <h2>Enter Password to View Logs</h2>
            <form method="post">
                <input type="password" name="password" required />
                <button type="submit">View Logs</button>
            </form>
        </body>
    </html>
    """

@app.post("/neon-logs", response_class=HTMLResponse)
async def post_neon_logs(password: str = Form(...)):
    import os
    if password != os.getenv("ADMIN_LOGS_PASSWORD"):
        return "<h2 style='color:red'>Invalid Password</h2><a href='/neon-logs'>Try again</a>"
    
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neon_keepalive.log")
    if not os.path.exists(log_file):
        return "<h2>No logs found.</h2><a href='/neon-logs'>Back</a>"
        
    with open(log_file, "r") as f:
        lines = f.readlines()
        
    top_50 = lines[-50:]
    logs_html = "<br>".join(top_50)
    
    return f"""
    <html>
        <body>
            <h2>Top 50 Logs</h2>
            <div style="background:#1e1e1e; color:#0f0; padding:10px; font-family:monospace; max-height:80vh; overflow-y:auto;">
                {logs_html}
            </div>
            <br>
            <a href='/neon-logs'>Back</a>
        </body>
    </html>
    """

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)