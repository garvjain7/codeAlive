from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import asyncio
import json
import re
import os
import uvicorn

from utils import validate_code, compress_code, generate_id
from redis_client import redis_client
from language_detector import detect_language
from image_router import router as image_router
from mailer import send_waitlist_email
from mongodb import waitlist_collection
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.include_router(image_router)

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
_RESERVED = frozenset({"editor", "waitlist", "static", "s", "new", "robots.txt", "sitemap.xml"})
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
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/editor", response_class=HTMLResponse)
async def editor(request: Request):
    """Fresh editor — no snippet loaded."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request":    request,
            "encoded":    "",
            "language":   "text",
            "highlights": "",
        },
    )


@app.get("/new")
async def new_snippet():
    """/new → redirect to /editor. Common convention, nice to have."""
    return RedirectResponse(url="/editor", status_code=302)


@app.get("/waitlist", response_class=HTMLResponse)
async def waitlist_page(request: Request):
    """Waitlist landing page."""
    return templates.TemplateResponse("waitlist.html", {"request": request})


@app.get("/robots.txt")
async def serve_robots_txt():
    """Serve robots.txt from root."""
    return FileResponse(os.path.join(BASE_DIR, "robots.txt"))


@app.get("/sitemap.xml")
async def serve_sitemap_xml():
    """Serve sitemap.xml from root."""
    return FileResponse(os.path.join(BASE_DIR, "sitemap.xml"))


@app.post("/waitlist")
async def waitlist_join(email: str = Form(...)):
    """
    Accept an email address for the collaboration rooms waitlist.

    Validation
    ----------
    - Basic format check (must contain @, domain, TLD)
    - Duplicate guard — silently succeeds if already on list
      (avoids leaking whether an email is registered)

    Storage
    -------
    Temporarily written to waitlist.json on disk.
    Replace _load_waitlist() / _save_waitlist() with a PostgreSQL
    INSERT when the DB is wired in — the route itself stays identical.
    """
    email = email.strip().lower()

    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(400, "Invalid email address")

    # 1. Check if already exists in MongoDB
    existing = waitlist_collection.find_one({"email": email})
    if existing:
        raise HTTPException(400, "Email is already added")

    # 2. Insert into MongoDB
    import datetime
    waitlist_collection.insert_one({
        "email":      email,
        "joined_at":  datetime.datetime.utcnow().isoformat(),
    })

    # 3. Send confirmation email
    send_waitlist_email(email)

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
    code: str        = Form(...),
    language: str    = Form("text"),
    highlights: str  = Form(""),
    custom_code: str = Form(None),
):
    """
    Save a snippet to Redis and return its shareable URL.

    Storage format
    --------------
    key   → code_id  (random 6-char slug, or user's custom slug)
    value → {gzip+base64_encoded_code}/{language}[/{highlights}]

    Example value:  H4sIAAAAAAAAA...==/python/L6-L14
    All new shareable URLs are under /s/{code_id}.
    """
    validate_code(code)

    # ── Resolve code_id ───────────────────────────────────────────────────────
    if custom_code:
        custom_code = custom_code.strip()

        if not custom_code:
            raise HTTPException(400, "Custom code cannot be empty")
        if len(custom_code) > 30:
            raise HTTPException(400, "Custom code too long (max 30 chars)")
        if custom_code in _RESERVED:
            raise HTTPException(400, "That slug is reserved — pick another")
        if redis_client.exists(custom_code):
            raise HTTPException(400, "Custom code already taken")

        code_id = custom_code

    else:
        code_id = generate_id()
        while redis_client.exists(code_id):
            code_id = generate_id()

    # ── Sanitise language ─────────────────────────────────────────────────────
    language = language.strip().lower() if language else "text"
    if not language or len(language) > 30:
        language = "text"

    # ── Persist ───────────────────────────────────────────────────────────────
    highlights = sanitise_highlights(highlights)
    encoded    = compress_code(code)

    # urlsafe-base64 never contains '/' so splitting on '/' is safe.
    if highlights:
        redis_client.set(code_id, f"{encoded}/{language}/{highlights}")
    else:
        redis_client.set(code_id, f"{encoded}/{language}")

    return {"url": f"/s/{code_id}"}


@app.get("/s/{code_id}", response_class=HTMLResponse)
async def view_snippet(request: Request, code_id: str):
    """
    Serve a shared snippet — new canonical URL format (/s/{code_id}).
    """
    stored = redis_client.get(code_id)
    if not stored:
        raise HTTPException(404, "Snippet not found")

    encoded, language, highlights = _parse_stored(stored)

    return templates.TemplateResponse(
        "index.html",
        {
            "request":    request,
            "encoded":    encoded,
            "language":   language,
            "highlights": highlights,
        },
    )


@app.get("/{code_id}", response_class=HTMLResponse)
async def legacy_snippet(code_id: str):
    """
    Legacy route — kept for backward compatibility with old shared links.

    If the code_id exists in Redis, issue a 301 permanent redirect to the
    canonical /s/{code_id} URL so browsers and search engines update their
    records automatically. Old links never break.

    Reserved path names that somehow fall through to this catch-all
    return 404 cleanly.
    """
    if code_id in _RESERVED:
        raise HTTPException(404, "Not found")

    stored = redis_client.get(code_id)
    if not stored:
        raise HTTPException(404, "Snippet not found")

    return RedirectResponse(url=f"/s/{code_id}", status_code=301)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)