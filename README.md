# CodeAlive

> Paste code. Get a link. No login, no setup, no expiration.

**CodeAlive** is a lightweight code sharing platform built for developers who want to share snippets instantly — with syntax highlighting, line highlighting, and shareable links that just work.

🌐 **Live:** [codealive.onrender.com](https://codealive.onrender.com)

---

## Features

### Core
- **Zero friction sharing** — paste code, hit share, get a link. No account, no configuration, no expiration.
- **Custom or random URLs** — choose your own slug (e.g. `codealive.onrender.com/my-bug`) or let the system generate a short unique one.
- **Language detection** — automatically detects the programming language as you type, with a 1s debounce and instant detection on paste.
- **Syntax highlighting** — powered by **CodeMirror 6** with a custom dark theme tuned for CodeAlive's palette. Supports 30+ dynamically loaded languages.
- **Copy to clipboard** — one-click copy of the code content.
- **Download** — download the snippet as a file with the correct extension based on detected language.

### Collaboration (Upcoming 🚀)
- **Real-time Shared Rooms** — Create a room, share the link, and write code together live. (Joining the waitlist gives early access).
- **Email Notifications** — Receive confirmation and launch updates via automated email system.

### Advanced
- **Strict Read-Only View Mode** — Shared links are strictly non-editable to prevent accidental changes.
- **Secure Snippet Protection** — Password-protect your snippets with automatic expiry and brute-force protection.
- **Line Highlighting** — Select any lines to mark them with colored bands that travel with the link. Supports multiple distinct highlight colors in a single snippet.
- **Interactive Code Widgets** — Attach screenshots or error logs inline with your code snippets using CodeMirror 6 `WidgetTypes` (e.g., `[image:xyz]`).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, Vanilla CSS, JavaScript (ES Modules / ESM) |
| Code Editor | **CodeMirror 6** (Loaded via `esm.sh`, no build step required) |
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Database | **PostgreSQL (Neon)** (Snippet storage, Auth, Access Control) |
| In-Memory Store | **Redis** (Session management) |
| File Storage | MongoDB Atlas (Images & Waitlist) |
| Email System | Gmail SMTP (smtplib) |
| Fonts | JetBrains Mono, Syne (Google Fonts) |
| Hosting | Render |

---

## Project Structure

```
codealive/
├── app.py                  # FastAPI entry point
├── api_snippets.py         # Snippet CRUD & Verification API
├── auth_router.py          # Authentication (Login/Signup) logic
├── db/                     # PostgreSQL Data Access Layer
├── static/                 # Frontend assets (ESM JS, CSS)
├── templates/              # Jinja2 HTML templates
├── redis_client.py         # Redis connection for sessions
├── mongodb.py              # MongoDB connection for images
└── requirements.txt        # Project dependencies
```

---

## Running Locally

### Prerequisites
- Python 3.10+
- PostgreSQL 14+
- Redis (running on `localhost:6379` or via `REDIS_URL`)
- MongoDB Atlas account (for images)
- Gmail App Password (for notifications)

### Setup

```bash
# Clone the repo
git clone https://github.com/garvjain7/codeAlive.git
cd codeAlive

# Install dependencies
pip install -r requirements.txt

# Create .env file from placeholders
# Add your MONGO_URI, MAIL_EMAIL, and MAIL_PASSWORD
```

### Environment Variables
The application requires a `.env` file with the following:
- `REDIS_URL`: Redis connection string (for sessions).
- `PG_HOST`, `PG_USER`, `PG_PASSWORD`, `PG_DB`: PostgreSQL credentials.
- `MONGO_URI`: MongoDB connection string (for images).
- `MAIL_EMAIL`: Your Gmail address.
- `MAIL_PASSWORD`: Your Gmail App Password.

---

## SEO & Accessibility
- **Sitemap**: Canonical `sitemap.xml` included for search engine discovery.
- **Responsiveness**: Fully optimized for mobile, tablet, and desktop viewports.
- **Robots.txt**: Standard configuration allowing indexing of all primary routes.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Tab` | Insert 2 spaces |
| `Escape` | Close share modal / dismiss highlight popup |

---

## License

MIT
