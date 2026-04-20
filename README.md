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
- **Syntax highlighting** — powered by Prism.js with a custom dark theme tuned for CodeAlive's palette. Supports 30+ languages.
- **Copy to clipboard** — one-click copy of the code content.
- **Download** — download the snippet as a file with the correct extension based on detected language.

### Collaboration (Upcoming 🚀)
- **Real-time Shared Rooms** — Create a room, share the link, and write code together live. (Joining the waitlist gives early access).
- **Email Notifications** — Receive confirmation and launch updates via automated email system.

### Advanced
- **Line Highlighting** — Select any lines to mark them with colored bands that travel with the link.
- **Code + Images** — Attach screenshots or error logs inline with your code snippets (Coming Soon).
- **Multi-language Detection** — Support for multiple languages in a single shareable file (In Dev).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, Vanilla CSS, JavaScript (ES6+) |
| Backend | Python 3.10+, FastAPI, Uvicorn |
| In-Memory Cache | Redis (Snippet storage) |
| Persistent Database | MongoDB Atlas (Images & Waitlist) |
| Email System | Gmail SMTP (smtplib) |
| Syntax Highlighting | Prism.js |
| Fonts | JetBrains Mono, Fraunces (Google Fonts) |
| Hosting | Render |

---

## Project Structure

```
codealive/
├── app.py                  # FastAPI app — routes, save/load logic
├── language_detector.py    # Language detection via codelang-detect
├── mongodb.py              # MongoDB Atlas connection & schemas
├── mailer.py               # SMTP client for email notifications
├── redis_client.py         # Redis connection for snippets
├── image_service.py        # Image compression & storage logic
├── utils.py                # Validation, gzip compression, ID generation
├── templates/
│   ├── index.html          # Main Editor UI
│   ├── home.html           # Marketing Landing Page
│   └── waitlist.html       # Waitlist Signup Page
└── static/
    ├── css/                # Modular stylesheets (home, waitlist)
    └── js/                 # Client-side logic (main, home, waitlist)
```

---

## Running Locally

### Prerequisites
- Python 3.10+
- Redis running on `localhost:6379`
- MongoDB Atlas account (or local MongoDB)
- Gmail App Password (for email features)

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
The application requires the following variables in a `.env` file:
- `REDIS_URL`: Connection string for Redis.
- `MONGO_URI`: Connection string for MongoDB Atlas.
- `MONGO_DB_NAME`: Database name (defaults to `codealive`).
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
