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
- **Syntax highlighting** — powered by Prism.js with a custom dark theme tuned for CodeAlive's palette. Supports 25+ languages.
- **Copy to clipboard** — one-click copy of the code content.
- **Download** — download the snippet as a file with the correct extension based on detected language.

### Line Highlighting
- **Select any lines** to mark them with a colored highlight band.
- **Multiple highlights** — add up to 5 independent highlight ranges, each in a distinct color.
- **Highlights travel with the link** — encoded in the share URL, restored for every viewer automatically.
- **Resize or remove** — select a highlighted region again to resize it, or remove it entirely via the popup.
- **Stale highlight cleanup** — if highlighted lines are deleted, the bands are automatically removed or clipped on the next edit.

### Editor
- **Mirror architecture** — transparent `<textarea>` on top of a Prism-highlighted `<pre>` layer, keeping native browser input behavior while rendering syntax colors.
- **Synchronized scroll** — line numbers, highlight bands, and the Prism layer all scroll in sync with the textarea.
- **Tab key support** — inserts 2 spaces instead of shifting focus.
- **Live line and character count** in the topbar.
- **Unsaved changes warning** — alerts when editing a shared snippet before generating a new link.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript (vanilla) |
| Backend | Python, FastAPI |
| Storage | Redis |
| Syntax Highlighting | Prism.js |
| Fonts | JetBrains Mono, Syne (Google Fonts) |
| Hosting | Render |

---

## Project Structure

```
codealive/
├── app.py                  # FastAPI app — routes, save/load logic
├── language_detector.py    # Language detection via codelang-detect
├── redis_client.py         # Redis connection
├── utils.py                # Validation, gzip compression, ID generation
├── templates/
│   └── index.html          # Single-page UI (CSS + HTML)
└── static/
    └── main.js             # All frontend logic
```

---

## How It Works

### Save flow
1. User pastes or types code into the editor
2. Language is detected via `POST /detect-language` (runs `codelang-detect` in a thread pool executor)
3. User clicks **share →**, optionally picks a custom slug
4. `POST /save` gzip-compresses the code, encodes it as URL-safe Base64, and stores it in Redis
5. Redis key: `code_id` → value: `{encoded}/{language}/{highlights}`
6. URL is pushed via `history.pushState` — no page reload

### Load flow
1. `GET /{code_id}` reads Redis, splits the stored value, and injects `__ENCODED__`, `__LANGUAGE__`, and `__HIGHLIGHTS__` into the HTML template via Jinja2
2. On page load, `main.js` decompresses the code client-side using the browser's `DecompressionStream` API
3. Language and highlights are applied immediately — no re-detection needed

### Storage format
```
{gzip+urlsafe_base64_code}/{language}/{highlight_ranges}

Example: H4sIAAAAAAAAA.../python/L4-L6,L12-L15
```

### Language detection state machine
```
idle → in-progress → done
                  ↘ failed
```
The `waitForResult()` Promise pattern ensures the Create Link button always waits for in-flight detection before saving — no races, no stale language tags.

---

## Running Locally

### Prerequisites
- Python 3.10+
- Redis running on `localhost:6379`

### Setup

```bash
# Clone the repo
git clone https://github.com/yourusername/codealive.git
cd codealive

# Install dependencies
pip install fastapi uvicorn redis codelang-detect jinja2 python-multipart

# Start Redis (if not already running)
redis-server

# Run the app
python app.py
```

App will be available at `http://localhost:8000`.

### Environment variables

For production, set `REDIS_URL` and update `redis_client.py` to use it:

```python
redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
```

---

## Limits

| Parameter | Limit |
|---|---|
| Max lines per snippet | 1,000 |
| Custom slug length | 30 characters |
| Allowed slug characters | Letters, numbers, hyphens |
| Language detection threshold | ≥ 8 lines or ≥ 100 characters |
| Detection cooldown | 2 seconds between calls |
| Detection timeout | 8 seconds |

---

## Supported Languages

`python` `javascript` `typescript` `java` `c` `cpp` `csharp` `rust` `go` `php` `ruby` `swift` `kotlin` `scala` `dart` `bash` `sql` `json` `yaml` `html` `css` `markdown` `r` `lua` `cobol`

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Tab` | Insert 2 spaces |
| `Escape` | Close share modal / dismiss highlight popup |

---

## License

MIT
