/* ═══════════════════════════════════════════════════════════════════════════
   CodeAlive — main.js
   ─────────────────────────────────────────────────────────────────────────
   Save flow  : code + detected-language → POST /save → short URL → pushState
   Load flow  : encoded + language (injected by backend) → decompress + render
                + apply Prism highlighting from URL language (no re-detection)
   Detection  : paste → immediate | typing → 1 s debounce | cooldown 2 s
                threshold ≥ 8 lines OR ≥ 100 chars
   Highlight  : Prism.js mirror overlay on top of transparent textarea
   Share gate : Create Link button waits for in-progress detection before /save
═══════════════════════════════════════════════════════════════════════════ */


// ── 1. DOM REFERENCES ─────────────────────────────────────────────────────────

const codeArea   = document.getElementById("codeArea");
const lineNums   = document.getElementById("line-numbers");
const lineInfo   = document.getElementById("lineInfo");
const charInfo   = document.getElementById("charInfo");

/* Syntax-highlight mirror */
const codeHighlight   = document.getElementById("code-highlight");
const codeHighlighted = document.getElementById("code-highlighted");

/* Language indicator in topbar */
const langDot   = document.getElementById("langDot");
const langBadge = document.getElementById("langBadge");

const copyCodeBtn = document.getElementById("copyCodeBtn");
const shareBtn    = document.getElementById("shareBtn");
const newBtn      = document.getElementById("newBtn");
const downloadBtn = document.getElementById("downloadBtn");

const shareBar = document.getElementById("share-bar");
const shareUrl = document.getElementById("shareUrl");
const copyBtn  = document.getElementById("copyBtn");

const errorBar  = document.getElementById("error-bar");
const toast     = document.getElementById("toast");
const viewBadge = document.getElementById("view-badge");

/* Share modal */
const shareModal       = document.getElementById("share-modal");
const createShare      = document.getElementById("createShare");
const cancelShare      = document.getElementById("cancelShare");
const modalCloseBtn    = document.getElementById("modalCloseBtn");
const customCode       = document.getElementById("customCode");
const charCounter      = document.getElementById("charCounter");
const urlInputWrap     = document.getElementById("urlInputWrap");
const validationIcon   = document.getElementById("validationIcon");
const urlHelper        = document.getElementById("urlHelper");
const customUrlSection = document.getElementById("customUrlSection");
const optionRandom     = document.getElementById("optionRandom");
const optionCustom     = document.getElementById("optionCustom");

const editWarning = document.getElementById("edit-warning");
const ewDismiss   = document.getElementById("ewDismiss");


// ── 2. CONSTANTS ──────────────────────────────────────────────────────────────

const MAX_LINES   = 1000;
const DEBOUNCE_MS = 1000;  // ms of inactivity before detection fires on typing
const COOLDOWN_MS = 2000;  // minimum ms between successive detection API calls
const MIN_LINES   = 8;     // threshold: need at least this many lines …
const MIN_CHARS   = 100;   // … OR this many characters to trigger detection


// ── 3. LANGUAGE DETECTION STATE MACHINE ──────────────────────────────────────
//
//  States:  idle → in-progress → done
//                             ↘ failed
//
//  The Promise/resolver pattern lets the Create-Link button await the
//  in-flight request without polling, without timers, without races.
// ─────────────────────────────────────────────────────────────────────────────

const detection = {
  status:   "idle",   // "idle" | "in-progress" | "done" | "failed"
  language: "text",

  _promise: null,     // Promise that resolves once detection finishes
  _resolve: null,     // its resolver

  /**
   * Returns a Promise that resolves to the detected language string.
   * If already done / failed, resolves immediately.
   */
  waitForResult() {
    if (this.status === "done" || this.status === "failed") {
      return Promise.resolve(this.language);
    }
    if (!this._promise) {
      this._promise = new Promise((res) => { this._resolve = res; });
    }
    return this._promise;
  },

  _flush(lang) {
    if (this._resolve) {
      this._resolve(lang);
      this._resolve = null;
      this._promise = null;
    }
  },

  /** Called when detection API returns successfully. */
  setResult(lang) {
    this.language = lang || "text";
    this.status   = "done";
    this._flush(this.language);
    updateLangBadge();
    mirrorToHighlight();
  },

  /** Called on network error or timeout. */
  setFailed() {
    this.language = "text";
    this.status   = "failed";
    this._flush("text");
    updateLangBadge();
  },

  /**
   * Full reset — use when content is completely replaced (new snippet / paste).
   * Flushes any pending waitForResult() with "text" BEFORE nulling refs,
   * so the Create Link button is never left permanently disabled.
   */
  reset() {
    this._flush("text");
    this.status   = "idle";
    this.language = "text";
    this._resolve = null;
    this._promise = null;
    updateLangBadge();
    mirrorToHighlight();
  },

  /**
   * Soft reset — content changed while editing.
   * Clears stale result so share button re-triggers detection,
   * but only transitions from terminal states (done/failed → idle).
   * Does NOT flush pending waiters; if detection is in-progress, leave it.
   */
  softReset() {
    if (this.status === "done" || this.status === "failed") {
      this.status   = "idle";
      this.language = "text";
      this._resolve = null;
      this._promise = null;
      updateLangBadge();
    }
  },
};


// ── 4. LANGUAGE DETECTION TRIGGER LOGIC ──────────────────────────────────────

let debounceTimer     = null;
let lastDetectionCall = 0;

/** Returns true if code is long enough to bother sending to the detector. */
function meetsThreshold(code) {
  return code.split("\n").length >= MIN_LINES || code.length >= MIN_CHARS;
}

/**
 * POST /detect-language and update detection state.
 *
 * try/catch scope is intentionally narrow — it only guards the fetch and
 * the JSON parse. detection.setResult() is called OUTSIDE the try block
 * so that a Prism crash inside setResult → mirrorToHighlight can never
 * be mistaken for a network failure and trigger setFailed().
 *
 * @param {string}  code      — current editor content
 * @param {boolean} immediate — if true, bypass the cooldown guard
 */
async function triggerDetection(code, immediate = false) {
  if (!code || !meetsThreshold(code)) return;

  const now = Date.now();
  if (!immediate && now - lastDetectionCall < COOLDOWN_MS) return;
  if (detection.status === "in-progress") return;

  detection.status  = "in-progress";
  lastDetectionCall = now;
  updateLangBadge();

  const controller = new AbortController();
  const timeoutId  = setTimeout(() => controller.abort(), 8000);

  // ── try guards ONLY the network request ──────────────────────────────────
  let data;
  try {
    const res = await fetch("/detect-language", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ code }),
      signal:  controller.signal,
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      detection.setFailed();
      return;
    }

    data = await res.json();
  } catch (err) {
    clearTimeout(timeoutId);
    detection.setFailed();
    return;
  }
  // ── setResult is OUTSIDE try — Prism crashes stay isolated ───────────────

  const lang = (data && typeof data.language === "string") ? data.language : "text";
  detection.setResult(lang);
}

/* ── Paste: full reset + immediate detection ────────────────────────────── */
codeArea.addEventListener("paste", () => {
  // setTimeout(0) lets the browser finish updating codeArea.value first
  setTimeout(() => {
    detection.reset();
    clearTimeout(debounceTimer);
    triggerDetection(codeArea.value, /* immediate */ true);
  }, 0);
});

/* ── Typing: soft reset + 1 s debounce ──────────────────────────────────── */
codeArea.addEventListener("input", () => {
  detection.softReset();
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    if (detection.status === "idle") {
      triggerDetection(codeArea.value);
    }
  }, DEBOUNCE_MS);
});


// ── 5. SYNTAX HIGHLIGHTING — PRISM MIRROR TECHNIQUE ──────────────────────────
//
//  Two absolutely-positioned layers inside #code-editor-container:
//    z-index 1: #code-highlight  <pre><code>  — Prism renders here
//                                              pointer-events: none
//    z-index 2: #codeArea        <textarea>   — captures all input
//                                              color: transparent
//                                              caret-color: var(--accent)
//
//  On every input / scroll event we:
//    • Re-render Prism into #code-highlighted  (mirrorToHighlight)
//    • Sync scrollTop/scrollLeft               (syncHighlightScroll)
// ─────────────────────────────────────────────────────────────────────────────

/** Safely escape HTML entities for the plain-text fallback. */
function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Re-render the Prism overlay to match textarea content + current language.
 *
 * Prism.highlight() is wrapped in its own isolated try/catch so that any
 * Prism-internal crash (e.g. tokenizePlaceholders on an unsupported grammar)
 * silently falls back to plain escaped text and never propagates upward.
 */
function mirrorToHighlight() {
  const code = codeArea.value;
  const lang = detection.language;

  let html;

  if (lang && lang !== "text" && typeof Prism !== "undefined" && Prism.languages[lang]) {
    try {
      html = Prism.highlight(code, Prism.languages[lang], lang);
      console.log("✅ Prism highlighted successfully, lang:", lang, "| output length:", html.length);
    } catch (err) {
      console.error("💥 Prism.highlight() threw for lang:", lang, "| error:", err);
      html = escapeHtml(code);
    }
  } else {
    // Log exactly WHY we fell into the plain-text path
    if (!lang || lang === "text") {
      console.log("🔤 mirrorToHighlight: lang is 'text' or empty, using plain text");
    } else if (typeof Prism === "undefined") {
      console.error("❌ mirrorToHighlight: Prism is NOT defined — scripts failed to load");
    } else if (!Prism.languages[lang]) {
      console.error("❌ mirrorToHighlight: Prism.languages['" + lang + "'] is undefined — component not loaded");
      console.log("📦 Available Prism languages:", Object.keys(Prism.languages));
    }
    html = escapeHtml(code);
  }

  codeHighlighted.innerHTML = html + "\n";
  syncHighlightScroll();
}

function syncHighlightScroll() {
  codeHighlight.scrollTop  = codeArea.scrollTop;
  codeHighlight.scrollLeft = codeArea.scrollLeft;
}

// Re-render overlay on every keystroke
codeArea.addEventListener("input", mirrorToHighlight);


// ── 6. LANGUAGE BADGE ─────────────────────────────────────────────────────────

function updateLangBadge() {
  const { status, language } = detection;

  if (status === "in-progress") {
    langDot.style.display   = "block";
    langBadge.style.display = "inline-flex";
    langBadge.textContent   = "detecting…";
    langBadge.classList.add("detecting");
  } else if (status === "done" && language && language !== "text") {
    langDot.style.display   = "block";
    langBadge.style.display = "inline-flex";
    langBadge.textContent   = language;
    langBadge.classList.remove("detecting");
  } else {
    langDot.style.display   = "none";
    langBadge.style.display = "none";
    langBadge.classList.remove("detecting");
  }
}


// ── 7. LINE NUMBERS ───────────────────────────────────────────────────────────

function updateLineNumbers() {
  const lines      = codeArea.value.split("\n");
  const count      = lines.length;
  const cursorPos  = codeArea.selectionStart;
  const activeLine = codeArea.value.substring(0, cursorPos).split("\n").length;

  lineInfo.textContent = `${count} line${count !== 1 ? "s" : ""}`;
  charInfo.textContent = `${codeArea.value.length} chars`;

  lineNums.innerHTML = lines
    .map((_, i) => `<span class="${i + 1 === activeLine ? "active" : ""}">${i + 1}</span>`)
    .join("");

  lineNums.scrollTop = codeArea.scrollTop;
}

codeArea.addEventListener("input",  updateLineNumbers);
codeArea.addEventListener("keyup",  updateLineNumbers);
codeArea.addEventListener("click",  updateLineNumbers);

// Sync all three scrollable panels together
codeArea.addEventListener("scroll", () => {
  lineNums.scrollTop = codeArea.scrollTop;
  syncHighlightScroll();
});

// Tab key: insert 2 spaces instead of leaving the textarea
codeArea.addEventListener("keydown", (e) => {
  if (e.key !== "Tab") return;
  e.preventDefault();

  const start = codeArea.selectionStart;
  const end   = codeArea.selectionEnd;

  codeArea.value =
    codeArea.value.substring(0, start) +
    "  " +
    codeArea.value.substring(end);

  codeArea.selectionStart = codeArea.selectionEnd = start + 2;

  updateLineNumbers();
  mirrorToHighlight();
});


// ── 8. EDIT WARNING ───────────────────────────────────────────────────────────

let editWarningDismissed = false;

function showEditWarning() {
  if (editWarningDismissed) return;
  editWarning.classList.add("show");
}
function hideEditWarning() {
  editWarning.classList.remove("show");
}

ewDismiss.addEventListener("click", () => {
  editWarningDismissed = true;
  hideEditWarning();
});

codeArea.addEventListener("input", () => {
  if (window.location.pathname !== "/") showEditWarning();
});


// ── 9. ERROR / TOAST HELPERS ──────────────────────────────────────────────────

function showError(msg, duration = 4000) {
  errorBar.textContent = msg;
  errorBar.classList.add("visible");
  setTimeout(() => errorBar.classList.remove("visible"), duration);
}

let toastTimer;
function showToast() {
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2000);
}


// ── 10. SHARE BAR ─────────────────────────────────────────────────────────────

function showShareBar(url) {
  shareUrl.value = url;
  shareBar.classList.add("visible");
}
function hideShareBar() {
  shareBar.classList.remove("visible");
}


// ── 11. OPTION CARD SELECTION ─────────────────────────────────────────────────

let selectedOption = "random";

function selectOption(option) {
  selectedOption = option;
  if (option === "random") {
    optionRandom.classList.add("selected");
    optionCustom.classList.remove("selected");
    customUrlSection.classList.remove("open");
  } else {
    optionCustom.classList.add("selected");
    optionRandom.classList.remove("selected");
    customUrlSection.classList.add("open");
    setTimeout(() => customCode.focus(), 80);
  }
}

optionRandom.addEventListener("click", () => selectOption("random"));
optionCustom.addEventListener("click", () => selectOption("custom"));


// ── 12. MODAL HELPERS ─────────────────────────────────────────────────────────

function openModal() {
  shareModal.classList.add("show");
  resetModalUI();
}
function closeModal() {
  shareModal.classList.remove("show");
}

function resetModalUI() {
  selectOption("random");

  customCode.value = "";
  charCounter.textContent = "0/30";
  charCounter.classList.remove("warn", "over");

  urlInputWrap.classList.remove("valid", "invalid");
  validationIcon.textContent = "";
  validationIcon.classList.remove("show", "ok", "err");

  urlHelper.textContent = "Letters, numbers and hyphens only";
  urlHelper.classList.remove("error-msg", "ok-msg");

  setCreateBtnNormal();
}

modalCloseBtn.addEventListener("click", closeModal);
cancelShare.addEventListener("click",   closeModal);

shareModal.addEventListener("click", (e) => {
  if (e.target === shareModal) closeModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && shareModal.classList.contains("show")) closeModal();
});


// ── 13. CUSTOM URL LIVE VALIDATION ────────────────────────────────────────────

const VALID_SLUG = /^[a-zA-Z0-9-]+$/;

function validateCustomInput(value) {
  const len = value.length;

  charCounter.textContent = `${len}/30`;
  charCounter.classList.toggle("warn", len >= 22 && len < 28);
  charCounter.classList.toggle("over", len >= 28);

  if (len === 0) {
    urlInputWrap.classList.remove("valid", "invalid");
    validationIcon.classList.remove("show", "ok", "err");
    validationIcon.textContent = "";
    urlHelper.textContent = "Letters, numbers and hyphens only";
    urlHelper.classList.remove("error-msg", "ok-msg");
    return;
  }

  const ok = VALID_SLUG.test(value) && !value.endsWith(" ");

  urlInputWrap.classList.toggle("valid",   ok);
  urlInputWrap.classList.toggle("invalid", !ok);

  validationIcon.textContent = ok ? "✓" : "✗";
  validationIcon.classList.toggle("ok",  ok);
  validationIcon.classList.toggle("err", !ok);
  validationIcon.classList.add("show");

  urlHelper.textContent = ok
    ? "Looks good!"
    : "Only letters, numbers and hyphens allowed";
  urlHelper.classList.toggle("ok-msg",    ok);
  urlHelper.classList.toggle("error-msg", !ok);
}

customCode.addEventListener("input", () => validateCustomInput(customCode.value));


// ── 14. CREATE BUTTON STATE HELPERS ──────────────────────────────────────────

function setCreateBtnLoading(msg = "creating...") {
  createShare.disabled  = true;
  createShare.innerHTML = `<span class="btn-spinner"></span>${msg}`;
}

function setCreateBtnNormal() {
  createShare.disabled  = false;
  createShare.innerHTML = "create link →";
}


// ── 15. PAGE MODE HELPERS ─────────────────────────────────────────────────────

function enterViewMode() {
  viewBadge.classList.add("show");
  downloadBtn.classList.add("show");
}

function enterHomeMode() {
  history.pushState({}, "", "/");

  codeArea.value    = "";
  codeArea.readOnly = false;

  hideShareBar();
  viewBadge.classList.remove("show");
  downloadBtn.classList.remove("show");

  hideEditWarning();
  editWarningDismissed = false;

  // reset() clears detection state, calls mirrorToHighlight() + updateLangBadge()
  clearTimeout(debounceTimer);
  detection.reset();

  updateLineNumbers();
  codeArea.focus();
}


// ── 16. SHARE BUTTON ──────────────────────────────────────────────────────────
//
//  Responsibilities (in order):
//    1. Guard: empty editor → show error, return
//    2. Kick off detection if not already running or done
//       a. Meets threshold → triggerDetection(immediate=true)
//       b. Below threshold → commit "text" immediately (no API call needed)
//    3. Open modal — always, regardless of detection state
//
//  The modal's Create Link button handles the wait if detection is mid-flight.
// ─────────────────────────────────────────────────────────────────────────────

shareBtn.addEventListener("click", () => {
  const code = codeArea.value.trim();

  if (!code) {
    showError("Nothing to share — paste some code first.");
    return;
  }

  if (detection.status === "idle" || detection.status === "failed") {
    if (meetsThreshold(code)) {
      clearTimeout(debounceTimer);
      triggerDetection(code, /* immediate */ true);
    } else {
      // Code too short — commit "text" right now, no need to hit the API
      detection.language = "text";
      detection.status   = "done";
      detection._flush("text");
      updateLangBadge();
    }
  }
  // status === "in-progress" or "done" → nothing to do here; modal handles it

  openModal();
});


// ── 17. CREATE LINK BUTTON (GATE) ─────────────────────────────────────────────
//
//  This button NEVER triggers detection — it only reads detection state.
//
//  Flow:
//    1. Validate code length + custom slug
//    2. If detection is "in-progress":
//         → show "Language detection in progress…" on button (disabled)
//         → await detection.waitForResult()     ← resolves when done or failed
//    3. POST /save with { code, language, [custom_code] }
//    4. Push new URL, show share bar, enter view mode, close modal
// ─────────────────────────────────────────────────────────────────────────────

createShare.addEventListener("click", async () => {
  const code = codeArea.value.trim();

  if (!code) {
    showError("Nothing to share.");
    return;
  }

  const lines = code.split("\n").length;
  if (lines > MAX_LINES) {
    showError(`Too long: ${lines} lines. Max is ${MAX_LINES}.`);
    return;
  }

  const custom = selectedOption === "custom" ? customCode.value : "";

  if (custom.endsWith(" ")) {
    showError("Custom code cannot end with a space.");
    return;
  }
  if (custom.length > 30) {
    showError("Custom code too long (max 30 characters).");
    return;
  }

  // ── Gate: hold button until detection resolves ─────────────────────────────
  if (detection.status === "in-progress") {
    setCreateBtnLoading("Language detection in progress…");
    await detection.waitForResult();
    // Detection is now "done" or "failed" — fall through to /save
  }

  // ── POST /save ─────────────────────────────────────────────────────────────
  const language = detection.language || "text";

  const formData = new FormData();
  formData.append("code", code);
  formData.append("language", language);
  if (custom.trim() !== "") {
    formData.append("custom_code", custom.trim());
  }

  setCreateBtnLoading("creating...");

  // try/catch here is legitimate — /save is a real network request that can fail
  try {
    const response = await fetch("/save", { method: "POST", body: formData });
    const data     = await response.json();

    if (!response.ok) {
      setCreateBtnNormal();
      showError(data.detail || "Failed to save.");
      return;
    }

    const fullUrl = window.location.origin + data.url;

    history.pushState({}, "", data.url);
    showShareBar(fullUrl);
    enterViewMode();
    closeModal();

    hideEditWarning();
    editWarningDismissed = false;

  } catch {
    setCreateBtnNormal();
    showError("Network error. Please try again.");
  }
});


// ── 18. COPY ──────────────────────────────────────────────────────────────────

copyBtn.addEventListener("click", () => {
  navigator.clipboard.writeText(shareUrl.value).then(showToast);
});

copyCodeBtn.addEventListener("click", () => {
  const code = codeArea.value;
  if (!code) return;
  navigator.clipboard.writeText(code).then(showToast);
});


// ── 19. NEW SNIPPET ───────────────────────────────────────────────────────────

newBtn.addEventListener("click", () => {
  enterHomeMode();
});


// ── 20. DOWNLOAD ──────────────────────────────────────────────────────────────

downloadBtn.addEventListener("click", () => {
  const code = codeArea.value;
  if (!code) return;

  // Use detected language as file extension, fallback to "txt"
  const lang = detection.language && detection.language !== "text"
    ? detection.language
    : "txt";
  const slug = window.location.pathname.replace(/^\//, "") || "code";
  const blob = new Blob([code], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");

  a.href     = url;
  a.download = `${slug}.${lang}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});


// ── 21. UNSAVED CHANGES WARNING ───────────────────────────────────────────────

window.addEventListener("beforeunload", (e) => {
  if (window.location.pathname === "/" && codeArea.value.trim().length > 0) {
    e.preventDefault();
    e.returnValue = "";
  }
});


// ── 22. DECODE + DECOMPRESS ───────────────────────────────────────────────────

async function decodeAndDecompress(encoded) {
  // URL-safe base64 → standard base64 → binary
  const std    = encoded.replace(/-/g, "+").replace(/_/g, "/");
  const padded = std + "=".repeat((4 - (std.length % 4)) % 4);
  const binary = atob(padded);

  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

  const ds     = new DecompressionStream("gzip");
  const writer = ds.writable.getWriter();
  writer.write(bytes);
  writer.close();

  const reader = ds.readable.getReader();
  const chunks = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }

  const total  = chunks.reduce((sum, c) => sum + c.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;

  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }

  return new TextDecoder().decode(result);
}


// ── 23. LOAD ENCODED SNIPPET (shared URL) ────────────────────────────────────
//
//  Language comes from window.__LANGUAGE__ (injected by GET /{code_id}).
//  Detection is NEVER triggered here — the stored language is authoritative.
//
//  try/catch here is legitimate — atob() and gzip decompression can both
//  throw on corrupt or malformed data, and we need to show a user-facing error.
// ─────────────────────────────────────────────────────────────────────────────

async function loadEncodedSnippet(encoded, language = "text") {
  try {
    const code = await decodeAndDecompress(encoded);

    codeArea.value    = code;
    codeArea.readOnly = false;

    // Pre-populate detection state from URL so share button skips re-detection
    detection.status   = "done";
    detection.language = language;

    updateLineNumbers();
    mirrorToHighlight();   // language is set → Prism highlights immediately
    updateLangBadge();

    showShareBar(window.location.href);
    enterViewMode();

  } catch (err) {
    showError("Failed to decode snippet.");
    console.error(err);
  }
}


// ── 24. INIT ──────────────────────────────────────────────────────────────────

(async function init() {
  updateLineNumbers();
  mirrorToHighlight();

  const encoded  = window.__ENCODED__  || "";
  const language = window.__LANGUAGE__ || "text";

  if (encoded.length > 0) {
    // Shared URL: load, highlight with stored language, skip detection entirely
    await loadEncodedSnippet(encoded, language);
  } else {
    codeArea.focus();
  }
})();