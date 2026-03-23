from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import asyncio
import re
import os
import uvicorn

from utils import validate_code, compress_code, generate_id
from redis_client import redis_client
from language_detector import detect_language

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Highlights sanitiser ─────────────────────────────────────────────────
# Expected format: "L6-L14,L32-L49" (no leading '#').
_HIGHLIGHTS_RE = re.compile(r"^L\d+(-L\d+)?(,L\d+(-L\d+)?)*$", re.IGNORECASE)

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


# ── Request model ──────────────────────────────────────────────────────────────

class DetectRequest(BaseModel):
    code: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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
    Save a snippet to Redis.

    Storage format
    --------------
    key   → code_id  (random 6-char slug, or user's custom slug)
    value → {gzip+base64_encoded_code}/{language}

    Example value:  H4sIAAAAAAAAA...==/python
    """
    validate_code(code)

    # ── Resolve code_id ────────────────────────────────────────────────────────
    if custom_code:
        custom_code = custom_code.rstrip()

        if len(custom_code) > 30:
            raise HTTPException(400, "Custom code too long (max 30 chars)")

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

    # ── Persist ────────────────────────────────────────────────────────────────
    highlights = str(sanitise_highlights(highlights))
    encoded = compress_code(code)

    # urlsafe-base64 never contains '/' so splitting on '/' is safe.
    if highlights:
        redis_client.set(code_id, f"{encoded}/{language}/{highlights}")
    else:
        redis_client.set(code_id, f"{encoded}/{language}")

    return {"url": f"/{code_id}"}


@app.get("/{code_id}", response_class=HTMLResponse)
async def get_code_page(request: Request, code_id: str):
    """
    Serve a shared snippet page.

    Reads the stored "{encoded}/{language}" value, splits on the LAST
    '/' (rsplit limit=1), and injects both parts into the template so
    the frontend can decode the code and apply syntax highlighting
    without running language detection again.
    """
    stored = redis_client.get(code_id)
    if not stored:
        raise HTTPException(404, "Code not found")

    # ── Parse stored value ────────────────────────────────────────────────────
    # New format: encoded/language/highlights
    # Old format: encoded/language
    # Legacy fallback: encoded (no language)
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

    # Never pass empty or suspiciously long values to the template.
    if not language or len(language) > 30:
        language = "text"

    highlights = sanitise_highlights(highlights)

    return templates.TemplateResponse(
        "index.html",
        {
            "request":  request,
            "encoded":  encoded,
            "language": language,
            "highlights": highlights,
        },
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)