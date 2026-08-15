# CodeAlive

> Paste code. Share files. No friction, no login required.

**CodeAlive** is a developer tool for sharing code snippets and files instantly — with syntax highlighting, live file previews, password protection, and shareable links that just work.

🌐 **Live:** [codealive.onrender.com](https://codealive.onrender.com)

---

## Features

### Code Snippets
- **Zero-friction sharing** — paste, hit share, get a permanent link. No account required.
- **Custom or random URLs** — pick your own slug (e.g. `/my-bug`) or get a generated short one.
- **30+ language auto-detection** — detects language as you type with 1s debounce, instant on paste.
- **Syntax highlighting** — powered by **CodeMirror 6** with a custom dark theme.
- **Line highlighting** — mark specific lines; the highlight travels with the link.
- **Code + images together** — attach screenshots or error logs inline with your snippet.
- **Password-protected snippets** — brute-force protected, with optional expiry.
- **Download & copy** — one-click copy or download with correct file extension.

### File Sharing
- **19+ file formats** — PDF, DOCX, XLSX, images (JPG, PNG, SVG, GIF, WebP), video (MP4, WebM, OGG), and audio (MP3).
- **Live in-browser preview** — no download, no external viewer:
  - PDF: page-by-page rendering via PDF.js
  - Word documents (DOCX): extracted via mammoth.js
  - Excel/spreadsheets (XLSX): rendered as tables via SheetJS
  - Images: native inline preview
  - Video: native HTML5 video player
  - Audio: custom glassmorphic audio player with seek bar, play/pause, time display, and mute
- **Size limits by type**: Docs & images: 500 KB · Video: 5 MB · Audio: 10 MB
- **Password protection** — optional password lock on shared file links.
- **Expiry control** — set a time-to-live on shared files.
- **Download tracking** — download count badge shown per file.
- **Instant shareable link** — same short-link system as code snippets (`/f/{id}`).

### Workspace (Authenticated Users)
- **My Files dashboard** — view all uploaded files with category icons, size, download counts, and expiry progress.
- **File management** — delete files (removes from R2 storage + DB), change password, extend expiry.
- **My Snippets** — manage all previously shared code snippets.

### Collaboration (Coming Soon 🚀)
- **Real-time shared rooms** — create a room, share the link, code together live.
- **Live cursors** — see who's editing where in real time.
- **Persistent room URLs** — rejoin any session by the same link.
- **Join the waitlist** at [codealive.onrender.com/waitlist](https://codealive.onrender.com/waitlist).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, Vanilla CSS, JavaScript (ES Modules) |
| Code Editor | **CodeMirror 6** (vendor-bundled, no build step) |
| File Previews | PDF.js, mammoth.js, SheetJS (xlsx) |
| Backend | Python 3.10+, **FastAPI**, Uvicorn (ASGI) |
| Database | **PostgreSQL (Neon)** via `asyncpg` |
| File Storage | **Cloudflare R2** (S3-compatible object storage) |
| In-Memory Store | **Redis** (session management, rolling TTL) |
| NoSQL | MongoDB Atlas (waitlist & image metadata) |
| Email | Gmail SMTP (async via FastAPI BackgroundTasks) |
| Fonts | JetBrains Mono, Fraunces (Google Fonts) |
| Hosting | **Render** |

---

## Project Structure

```
codeAlive/
├── app.py                    # FastAPI entry point, routing, reserved slugs
├── api/
│   ├── api_snippets.py       # Snippet CRUD & verification
│   ├── auth_router.py        # Login / Signup / Logout
│   ├── file_router.py        # File upload, share, preview endpoints
│   ├── profile_router.py     # User profile API
│   └── workspace_router.py   # Workspace dashboard & file management API
├── db/                       # PostgreSQL Data Access Layer (asyncpg)
├── services/
│   ├── file_service.py       # File validation, type detection, R2 upload
│   ├── image_service.py      # Snippet image attachment handling
│   ├── language_detector.py  # Language auto-detection
│   └── mail_service_v2.py    # Email sending helpers
├── core/
│   ├── config.py             # Environment config & secrets
│   └── r2_client.py          # Cloudflare R2 S3 client
├── ot_collab/                # Real-time OT collaboration engine (rooms)
├── static/
│   ├── css/                  # Theme, home, auth, workspace, file-viewer styles
│   ├── import.js             # File import modal, preview rendering, audio player
│   ├── workspace.js          # Workspace dashboard & file cards
│   ├── file-viewer.js        # Shared file view & unlock flow
│   ├── error-service.js      # Centralized error toast system
│   └── vendor/               # Bundled CodeMirror 6 & language packages
├── templates/                # Jinja2 HTML templates
│   ├── home.html             # Marketing homepage
│   ├── import.html           # File import & preview page
│   ├── workspace.html        # Authenticated workspace dashboard
│   ├── profile.html          # User profile
│   └── waitlist.html         # Collaboration waitlist
├── tests/                    # Pytest test suite
├── robots.txt                # SEO crawler config
├── sitemap.xml               # Canonical sitemap
└── requirements.txt          # Python dependencies
```

---

### Running Locally

#### 1. Remote API Proxy Mode (Recommended for UI Development)
If you are working on the frontend (HTML/CSS/JS) and do not want to set up local databases or configure secret API keys:

```bash
# Copy template environment file
cp .env.example .env

# Start server in remote proxy mode
python app.py
```

Set `REMOTE_API_MODE=true` in `.env`. Local FastAPI will serve frontend templates and static files locally while transparently proxying backend/API calls to `https://codealive.onrender.com`.

#### 2. Full Local Stack Mode
If you are working on backend features locally:

```bash
# Clone the repo
git clone https://github.com/garvjain7/codeAlive.git
cd codeAlive

# Install dependencies
pip install -r requirements.txt

# Create a .env file and fill in the required values (see below)
cp .env.example .env

# Start the server
uvicorn app:app --reload
```

### Environment Variables

| Variable | Description |
|---|---|
| `REMOTE_API_MODE` | Set to `true` for frontend UI development without local DB keys |
| `LIVE_API_URL` | Deployed backend URL for proxying (defaults to `https://codealive.onrender.com`) |
| `DB_URL` | PostgreSQL connection string (Neon or local) |
| `REDIS_URL` | Redis connection string (Render instance or `redis://localhost:6379`). In `core/redis_client.py`, `REDIS_URL` is read from environment. For local Redis testing without an environment variable, `core/redis_client.py` falls back to `redis://localhost:6379`. |
| `MONGO_URI` | MongoDB Atlas connection string |
| `R2_ACCOUNT_ID` | Cloudflare R2 account ID |
| `R2_ACCESS_KEY` | Cloudflare R2 access key |
| `R2_SECRET_KEY` | Cloudflare R2 secret key |
| `R2_BUCKET_NAME` | R2 bucket name for file uploads |
| `R2_PUBLIC_URL` | Public URL prefix for R2 files |
| `MAIL_EMAIL` | Gmail address for sending notifications |
| `MAIL_PASSWORD` | Gmail App Password |
| `SECRET_KEY` | FastAPI session secret key |

---

## SEO & Accessibility
- **Sitemap** — `sitemap.xml` listing all public pages for search engine discovery.
- **Robots.txt** — crawl rules disallowing private routes (`/workspace`, `/profile`, `/api/`) and explicitly allowing public ones.
- **Open Graph** — `og:title`, `og:description`, `og:url` meta tags on all pages including dynamic file share pages.
- **Google Analytics** — `gtag.js` integration on all pages.
- **Responsive** — fully optimized for mobile, tablet, and desktop.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Tab` | Insert 2 spaces in editor |
| `Escape` | Close share modal / dismiss popups |

---

## Tests

```bash
python -m pytest -q
```

10 tests covering file validation, snippet API, editor import, and vendor routes.

---

## License

MIT © 2026 Garv Jain
