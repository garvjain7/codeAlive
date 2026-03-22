"""
language_detector.py — CodeAlive
Uses codelang-detect to identify the programming language of a code snippet.
Returns a Prism-compatible language name (e.g. "python", "javascript")
or "text" as the universal fallback.

pip install codelang-detect
"""

import hashlib
from typing import Dict

from codelang_detect import detect as _lib_detect

# ── In-memory cache: sha256(code) → language ─────────────────────────────────
_cache: Dict[str, str] = {}

# ── Extension → Prism language name ──────────────────────────────────────────
# codelang-detect returns file extensions (e.g. 'py', 'js', 'cs').
# We map every known extension to the exact string Prism.js expects.
_EXT_TO_LANG: Dict[str, str] = {
    # ── Systems / compiled ────────────────────────────────────────────────────
    "c":     "c",
    "cpp":   "cpp",
    "cs":    "csharp",
    "rs":    "rust",
    "go":    "go",
    # ── JVM ───────────────────────────────────────────────────────────────────
    "java":  "java",
    "kt":    "kotlin",
    "scala": "scala",
    # ── Scripting ─────────────────────────────────────────────────────────────
    "py":    "python",
    "rb":    "ruby",
    "php":   "php",
    "lua":   "lua",
    "pl":    "perl",
    # ── Web ───────────────────────────────────────────────────────────────────
    "js":    "javascript",
    "ts":    "typescript",
    "html":  "html",
    "css":   "css",
    "jsx":   "jsx",
    "tsx":   "tsx",
    # ── Mobile ────────────────────────────────────────────────────────────────
    "swift": "swift",
    "dart":  "dart",
    # ── Shell ─────────────────────────────────────────────────────────────────
    "sh":    "bash",
    "bash":  "bash",
    "zsh":   "bash",
    "ps1":   "powershell",
    # ── Data / config ─────────────────────────────────────────────────────────
    "sql":   "sql",
    "json":  "json",
    "yaml":  "yaml",
    "yml":   "yaml",
    "toml":  "toml",
    "xml":   "xml",
    # ── Docs ──────────────────────────────────────────────────────────────────
    "md":    "markdown",
    "r":     "r",
    # ── Legacy ────────────────────────────────────────────────────────────────
    "cbl":   "cobol",
}


# ── Public API ────────────────────────────────────────────────────────────────

def detect_language(code: str) -> str:
    """
    Detect the programming language of *code*.

    Steps
    -----
    1. Return "text" immediately for empty / whitespace-only input.
    2. Check SHA-256 cache — return cached result if present.
    3. Delegate to codelang-detect.
    4. Map the returned file extension to a Prism-compatible name.
    5. Cache and return; fall back to "text" on any error.
    """
    if not code or not code.strip():
        return "text"

    # ── Cache lookup ──────────────────────────────────────────────────────────
    code_hash = hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest()
    if code_hash in _cache:
        return _cache[code_hash]

    # ── Detection ─────────────────────────────────────────────────────────────
    try:
        ext    = _lib_detect(code)                        # e.g. "py", "unknown"
        result = _EXT_TO_LANG.get(ext, "text") if ext and ext != "unknown" else "text"
    except Exception:
        result = "text"

    # ── Cache & return ────────────────────────────────────────────────────────
    _cache[code_hash] = result
    return result