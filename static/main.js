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

const codeArea = document.getElementById("codeArea");
const lineNums = document.getElementById("line-numbers");
const lineInfo = document.getElementById("lineInfo");
const charInfo = document.getElementById("charInfo");

/* Syntax-highlight mirror */
const codeHighlight = document.getElementById("code-highlight");
const codeHighlighted = document.getElementById("code-highlighted");

/* Line highlight bands (behind Prism) */
const lineHighlightLayer = document.getElementById("line-highlight-layer");
const highlightBands = document.getElementById("highlight-bands");

/* Floating popup for highlight selection */
const highlightPopup = document.getElementById("highlight-popup");
const popupHighlightBtn = document.getElementById("popupHighlightBtn");
const popupRemoveBtn = document.getElementById("popupRemoveBtn");

/* Language indicator in topbar */
const langDot = document.getElementById("langDot");
const langBadge = document.getElementById("langBadge");

const copyCodeBtn = document.getElementById("copyCodeBtn");
const shareBtn = document.getElementById("shareBtn");
const newBtn = document.getElementById("newBtn");
const downloadBtn = document.getElementById("downloadBtn");

const shareBar = document.getElementById("share-bar");
const shareUrl = document.getElementById("shareUrl");
const copyBtn = document.getElementById("copyBtn");

const errorBar = document.getElementById("error-bar");
const toast = document.getElementById("toast");
const viewBadge = document.getElementById("view-badge");

/* Share modal */
const shareModal = document.getElementById("share-modal");
const createShare = document.getElementById("createShare");
const cancelShare = document.getElementById("cancelShare");
const modalCloseBtn = document.getElementById("modalCloseBtn");
const customCode = document.getElementById("customCode");
const charCounter = document.getElementById("charCounter");
const urlInputWrap = document.getElementById("urlInputWrap");
const validationIcon = document.getElementById("validationIcon");
const urlHelper = document.getElementById("urlHelper");
const customUrlSection = document.getElementById("customUrlSection");
const optionRandom = document.getElementById("optionRandom");
const optionCustom = document.getElementById("optionCustom");

const editWarning = document.getElementById("edit-warning");
const ewDismiss = document.getElementById("ewDismiss");
const editorHintEmpty     = document.getElementById("editor-hint-empty");
const editorHintHighlight = document.getElementById("editor-hint-highlight");

/* How to Highlight modal */
const highlightModal = document.getElementById("highlightModal");
const highlightCloseBtn = document.getElementById("highlightCloseBtn");
const highlightGotIt = document.getElementById("highlightGotIt");
const howItWorksBtn = document.getElementById("howItWorksBtn");

// ── 2. CONSTANTS ──────────────────────────────────────────────────────────────

const MAX_LINES = 1000;
const DEBOUNCE_MS = 1000; // ms of inactivity before detection fires on typing
const COOLDOWN_MS = 2000; // minimum ms between successive detection API calls
const MIN_LINES = 8; // threshold: need at least this many lines …
const MIN_CHARS = 100; // … OR this many characters to trigger detection

/* Must match #codeArea / #code-highlight CSS exactly */
const LINE_HEIGHT = 22; // px — line-height in editor
const PADDING_TOP = 18; // px — padding-top in editor

// Highlight colors taken from existing Prism palette so the bands feel native.
const COLOR_POOL = [
  { bg: "rgba(63,  224, 160, 0.10)", border: "#3fe0a0" }, // accent green
  { bg: "rgba(123, 159, 255, 0.10)", border: "#7b9fff" }, // keyword blue
  { bg: "rgba(245, 169, 127, 0.10)", border: "#f5a97f" }, // number orange
  { bg: "rgba(232, 201, 110, 0.10)", border: "#e8c96e" }, // class yellow
  { bg: "rgba(240, 128, 128, 0.10)", border: "#f08080" }, // error red
];

// highlights: Array of { id, start, end } where start/end are 1-based line numbers.
let highlights = [];
let pendingSelection = null; // { startLine, endLine, targetHighlight }
let hlIdCounter = 0;

function nextHlId() {
  return `hl_${Date.now()}_${hlIdCounter++}`;
}

// "L6-L14,L32-L49" → [{id,start,end}, ...]
function parseHighlights(str) {
  if (!str || !str.trim()) return [];
  return str
    .split(",")
    .map((part) => {
      const m = part.trim().match(/^L(\d+)(?:-L(\d+))?$/i);
      if (!m) return null;
      const start = parseInt(m[1], 10);
      const end = m[2] ? parseInt(m[2], 10) : start;
      if (isNaN(start) || isNaN(end) || start < 1 || end < start) return null;
      return { id: nextHlId(), start, end };
    })
    .filter(Boolean);
}

// [{ start, end }, ...] → "L6-L14,L32-L49"
function serializeHighlights(hls) {
  if (!hls.length) return "";
  return [...hls]
    .sort((a, b) => a.start - b.start)
    .map((h) => (h.start === h.end ? `L${h.start}` : `L${h.start}-L${h.end}`))
    .join(",");
}

function syncHighlightBandsScroll() {
  // translate scrollTop so bands line up with code text.
  highlightBands.style.transform = `translateY(-${codeArea.scrollTop}px)`;
}

function renderHighlights() {
  highlightBands.innerHTML = "";

  highlights.forEach((h, i) => {
    const color = COLOR_POOL[i % COLOR_POOL.length];
    const band = document.createElement("div");
    band.className = "highlight-band";
    band.style.top = `${PADDING_TOP + (h.start - 1) * LINE_HEIGHT}px`;
    band.style.height = `${(h.end - h.start + 1) * LINE_HEIGHT}px`;
    band.style.background = color.bg;
    band.style.borderLeft = `3px solid ${color.border}`;
    highlightBands.appendChild(band);
  });

  syncHighlightBandsScroll();
}

function hideHighlightPopup() {
  highlightPopup.classList.remove("show");
  pendingSelection = null;
}

function showHighlightPopup(startLine, endLine, targetHighlight) {
  const rect = codeArea.getBoundingClientRect();

  const rawTop =
    rect.top + PADDING_TOP + endLine * LINE_HEIGHT - codeArea.scrollTop + 6;
  const top = Math.min(rawTop, window.innerHeight - 52);

  const lnWidth = parseInt(
    getComputedStyle(document.documentElement).getPropertyValue("--ln-width") ||
      "52",
    10,
  );
  const left = rect.left + lnWidth + 12;

  highlightPopup.style.top = `${top}px`;
  highlightPopup.style.left = `${left}px`;
  pendingSelection = { startLine, endLine, targetHighlight };

  if (targetHighlight) {
    popupHighlightBtn.textContent = "↔ resize highlighted lines";
    popupHighlightBtn.style.display = "inline-flex";
    popupRemoveBtn.style.display = "inline-flex";
  } else {
    popupHighlightBtn.textContent = "⬛ highlight lines";
    popupHighlightBtn.style.display = "inline-flex";
    popupRemoveBtn.style.display = "none";
  }

  highlightPopup.classList.add("show");
}

function onHighlightsChanged() {
  renderHighlights();
}

function addHighlight(startLine, endLine) {
  highlights.push({ id: nextHlId(), start: startLine, end: endLine });
  onHighlightsChanged();
}

function removeHighlight(id) {
  highlights = highlights.filter((h) => h.id !== id);
  onHighlightsChanged();
}

function updateHighlight(id, startLine, endLine) {
  const h = highlights.find((x) => x.id === id);
  if (!h) return;
  h.start = startLine;
  h.end = endLine;
  onHighlightsChanged();
}

function overlapLen(h, startLine, endLine) {
  // Inclusive overlap length in lines.
  const a = Math.max(h.start, startLine);
  const b = Math.min(h.end, endLine);
  if (b < a) return 0;
  return b - a + 1;
}

function handleTextSelection() {
  // Popup only appears on '/' (editor mode). On shared URLs this stays hidden.
  // if (window.location.pathname !== "/") return;
  if (window.location.pathname.length > 1) return;

  const { selectionStart, selectionEnd } = codeArea;
  if (selectionStart === selectionEnd) {
    hideHighlightPopup();
    return;
  }

  const textBefore = codeArea.value.substring(0, selectionStart);
  const textSelected = codeArea.value.substring(selectionStart, selectionEnd);

  const startLine = textBefore.split("\n").length;
  const endLine = startLine + textSelected.split("\n").length - 1;

  // Find all highlights that overlap this selection.
  // If multiple overlaps exist, edit the one with the largest overlap length.
  const overlappingHighlights = highlights.filter(
    (h) => !(h.end < startLine || h.start > endLine),
  );

  let target = null;
  if (overlappingHighlights.length > 0) {
    // Prefer highlights that contain the selection start line.
    // This makes resizing deterministic when multiple highlights overlap
    // on common lines.
    const containingStart = overlappingHighlights.filter(
      (h) => h.start <= startLine && h.end >= startLine,
    );

    const pool =
      containingStart.length > 0 ? containingStart : overlappingHighlights;
    pool.sort((a, b) => {
      const da = overlapLen(a, startLine, endLine);
      const db = overlapLen(b, startLine, endLine);
      if (db !== da) return db - da; // larger overlap first
      // Tie-break: choose the one with later start (more specific)
      return b.start - a.start;
    });

    target = pool[0];
  }

  showHighlightPopup(startLine, endLine, target);
}

// Show popup after mouse selection
codeArea.addEventListener("mouseup", handleTextSelection);
// Show popup after keyboard selection (Shift+Arrow)
codeArea.addEventListener("keyup", (e) => {
  if (e.shiftKey) handleTextSelection();
});

popupHighlightBtn.addEventListener("click", () => {
  if (!pendingSelection) return;
  if (pendingSelection.targetHighlight) {
    updateHighlight(
      pendingSelection.targetHighlight.id,
      pendingSelection.startLine,
      pendingSelection.endLine,
    );
  } else {
    addHighlight(pendingSelection.startLine, pendingSelection.endLine);
  }
  hideHighlightPopup();
  codeArea.focus();
});

popupRemoveBtn.addEventListener("click", () => {
  if (!pendingSelection || !pendingSelection.targetHighlight) return;
  removeHighlight(pendingSelection.targetHighlight.id);
  hideHighlightPopup();
  codeArea.focus();
});

document.addEventListener("mousedown", (e) => {
  if (!highlightPopup.contains(e.target) && e.target !== codeArea)
    hideHighlightPopup();
});

// Hide popup when the user types + clean stale highlights
codeArea.addEventListener("input", () => {
  hideHighlightPopup();
  const totalLines = codeArea.value.split("\n").length;
  highlights = highlights
    .filter(h => h.start <= totalLines)
    .map(h => ({ ...h, end: Math.min(h.end, totalLines) }));
  renderHighlights();
});

// ── 3. LANGUAGE DETECTION STATE MACHINE ──────────────────────────────────────
//
//  States:  idle → in-progress → done
//                             ↘ failed
//
//  The Promise/resolver pattern lets the Create-Link button await the
//  in-flight request without polling, without timers, without races.
// ─────────────────────────────────────────────────────────────────────────────

const detection = {
  status: "idle", // "idle" | "in-progress" | "done" | "failed"
  language: "text",

  _promise: null, // Promise that resolves once detection finishes
  _resolve: null, // its resolver

  /**
   * Returns a Promise that resolves to the detected language string.
   * If already done / failed, resolves immediately.
   */
  waitForResult() {
    if (this.status === "done" || this.status === "failed") {
      return Promise.resolve(this.language);
    }
    if (!this._promise) {
      this._promise = new Promise((res) => {
        this._resolve = res;
      });
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
    this.status = "done";
    this._flush(this.language);
    updateLangBadge();
    mirrorToHighlight();
  },

  /** Called on network error or timeout. */
  setFailed() {
    this.language = "text";
    this.status = "failed";
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
    this.status = "idle";
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
      this.status = "idle";
      this.language = "text";
      this._resolve = null;
      this._promise = null;
      updateLangBadge();
    }
  },
};

// ── 4. LANGUAGE DETECTION TRIGGER LOGIC ──────────────────────────────────────

let debounceTimer = null;
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

  detection.status = "in-progress";
  lastDetectionCall = now;
  updateLangBadge();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);

  // ── try guards ONLY the network request ──────────────────────────────────
  let data;
  try {
    const res = await fetch("/detect-language", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
      signal: controller.signal,
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

  const lang =
    data && typeof data.language === "string" ? data.language : "text";
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
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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

  if (
    lang &&
    lang !== "text" &&
    typeof Prism !== "undefined" &&
    Prism.languages[lang]
  ) {
    try {
      html = Prism.highlight(code, Prism.languages[lang], lang);
      console.log(
        "✅ Prism highlighted successfully, lang:",
        lang,
        "| output length:",
        html.length,
      );
    } catch (err) {
      console.error(
        "💥 Prism.highlight() threw for lang:",
        lang,
        "| error:",
        err,
      );
      html = escapeHtml(code);
    }
  } else {
    // Log exactly WHY we fell into the plain-text path
    if (!lang || lang === "text") {
      console.log(
        "🔤 mirrorToHighlight: lang is 'text' or empty, using plain text",
      );
    } else if (typeof Prism === "undefined") {
      console.error(
        "❌ mirrorToHighlight: Prism is NOT defined — scripts failed to load",
      );
    } else if (!Prism.languages[lang]) {
      console.error(
        "❌ mirrorToHighlight: Prism.languages['" +
          lang +
          "'] is undefined — component not loaded",
      );
      console.log(
        "📦 Available Prism languages:",
        Object.keys(Prism.languages),
      );
    }
    html = escapeHtml(code);
  }

  codeHighlighted.innerHTML = html + "\n";
  syncHighlightScroll();
}

function syncHighlightScroll() {
  codeHighlight.scrollTop = codeArea.scrollTop;
  codeHighlight.scrollLeft = codeArea.scrollLeft;
}

// Re-render overlay on every keystroke
codeArea.addEventListener("input", mirrorToHighlight);

// ── 6. LANGUAGE BADGE ─────────────────────────────────────────────────────────

function updateLangBadge() {
  const { status, language } = detection;

  if (status === "in-progress") {
    langDot.style.display = "block";
    langBadge.style.display = "inline-flex";
    langBadge.textContent = "detecting…";
    langBadge.classList.add("detecting");
  } else if (status === "done" && language && language !== "text") {
    langDot.style.display = "block";
    langBadge.style.display = "inline-flex";
    langBadge.textContent = language;
    langBadge.classList.remove("detecting");
  } else {
    langDot.style.display = "none";
    langBadge.style.display = "none";
    langBadge.classList.remove("detecting");
  }
}

// ── 7. LINE NUMBERS ───────────────────────────────────────────────────────────

function updateLineNumbers() {
  const lines = codeArea.value.split("\n");
  const count = lines.length;
  const cursorPos = codeArea.selectionStart;
  const activeLine = codeArea.value.substring(0, cursorPos).split("\n").length;

  lineInfo.textContent = `${count} line${count !== 1 ? "s" : ""}`;
  charInfo.textContent = `${codeArea.value.length} chars`;

  lineNums.innerHTML = lines
    .map(
      (_, i) =>
        `<span class="${i + 1 === activeLine ? "active" : ""}">${i + 1}</span>`,
    )
    .join("");

  lineNums.scrollTop = codeArea.scrollTop;
}

codeArea.addEventListener("input", updateLineNumbers);
codeArea.addEventListener("keyup", updateLineNumbers);
codeArea.addEventListener("click", updateLineNumbers);

// Sync all three scrollable panels together
codeArea.addEventListener("scroll", () => {
  lineNums.scrollTop = codeArea.scrollTop;
  syncHighlightScroll();
  syncHighlightBandsScroll();
});

// Tab key: insert 2 spaces instead of leaving the textarea
codeArea.addEventListener("keydown", (e) => {
  if (e.key !== "Tab") return;
  e.preventDefault();

  const start = codeArea.selectionStart;
  const end = codeArea.selectionEnd;

  codeArea.value =
    codeArea.value.substring(0, start) + "  " + codeArea.value.substring(end);

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
cancelShare.addEventListener("click", closeModal);

shareModal.addEventListener("click", (e) => {
  if (e.target === shareModal) closeModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (shareModal.classList.contains("show")) closeModal();
    hideHighlightPopup();
  }
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

  urlInputWrap.classList.toggle("valid", ok);
  urlInputWrap.classList.toggle("invalid", !ok);

  validationIcon.textContent = ok ? "✓" : "✗";
  validationIcon.classList.toggle("ok", ok);
  validationIcon.classList.toggle("err", !ok);
  validationIcon.classList.add("show");

  urlHelper.textContent = ok
    ? "Looks good!"
    : "Only letters, numbers and hyphens allowed";
  urlHelper.classList.toggle("ok-msg", ok);
  urlHelper.classList.toggle("error-msg", !ok);
}

customCode.addEventListener("input", () =>
  validateCustomInput(customCode.value),
);

// ── 14. CREATE BUTTON STATE HELPERS ──────────────────────────────────────────

function setCreateBtnLoading(msg = "creating...") {
  createShare.disabled = true;
  createShare.innerHTML = `<span class="btn-spinner"></span>${msg}`;
}

function setCreateBtnNormal() {
  createShare.disabled = false;
  createShare.innerHTML = "create link →";
}

// ── 15. PAGE MODE HELPERS ─────────────────────────────────────────────────────

function enterViewMode() {
  viewBadge.classList.add("show");
  downloadBtn.classList.add("show");
  editorHintEmpty.classList.add("hidden");
  editorHintHighlight.classList.add("hidden");
}

function enterHomeMode() {
  history.pushState({}, "", "/");

  codeArea.value = "";
  codeArea.readOnly = false;

  hideShareBar();
  viewBadge.classList.remove("show");
  downloadBtn.classList.remove("show");

  hideEditWarning();
  editWarningDismissed = false;

  // reset() clears detection state, calls mirrorToHighlight() + updateLangBadge()
  clearTimeout(debounceTimer);
  detection.reset();

  highlights = [];
  renderHighlights();
  hideHighlightPopup();

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
      detection.status = "done";
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
  const highlightsStr = serializeHighlights(highlights);
  // if (highlightsStr) formData.append("highlights", highlightsStr);
  // if (custom.trim() !== "") {popupHighlightBtn
  //   formData.append("custom_code", custom.trim());
  // }

  formData.append("highlights", highlightsStr || "");
  formData.append("custom_code", custom.trim() || "");

  setCreateBtnLoading("creating...");

  // try/catch here is legitimate — /save is a real network request that can fail
  try {
    const response = await fetch("/save", { method: "POST", body: formData });
    const data = await response.json();

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
    hideHighlightPopup();

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
  const lang =
    detection.language && detection.language !== "text"
      ? detection.language
      : "txt";
  const slug = window.location.pathname.replace(/^\//, "") || "code";
  const blob = new Blob([code], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");

  a.href = url;
  a.download = `${slug}.${lang}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// Open modal
function openHighlightModal() {
  console.log("Modal element:", highlightModal);
  if (highlightModal) {
    highlightModal.classList.remove("hidden");
  }
}

// Close modal
function closeHighlightModal() {
  if (highlightModal) {
    highlightModal.classList.add("hidden");
  }
}

// Close actions (X button + Got it)
if (highlightCloseBtn) {
  highlightCloseBtn.addEventListener("click", closeHighlightModal);
}

if (highlightGotIt) {
  highlightGotIt.addEventListener("click", closeHighlightModal);
}

// Open from "How it works" button (ALWAYS works)
if (howItWorksBtn) {
  howItWorksBtn.addEventListener("click", openHighlightModal);
}

// ===============================
// 🚀 Trigger AFTER welcome box hides
// ===============================

function triggerHighlightAfterWelcome() {
  // ✅ Only show on homepage
  const isHomePage = window.location.pathname === "/";

  // ✅ Check if already seen
  const seen = localStorage.getItem("seenHighlightGuide");

  if (!seen && isHomePage) {
    setTimeout(() => {
      openHighlightModal();
      localStorage.setItem("seenHighlightGuide", "true");
    }, 500);
  }
}

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
  const std = encoded.replace(/-/g, "+").replace(/_/g, "/");
  const padded = std + "=".repeat((4 - (std.length % 4)) % 4);
  const binary = atob(padded);

  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

  const ds = new DecompressionStream("gzip");
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

  const total = chunks.reduce((sum, c) => sum + c.length, 0);
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

async function loadEncodedSnippet(
  encoded,
  language = "text",
  highlightsStr = "",
) {
  try {
    const code = await decodeAndDecompress(encoded);

    codeArea.value = code;
    codeArea.readOnly = false;

    // Pre-populate detection state from URL so share button skips re-detection
    detection.status = "done";
    detection.language = language;

    // Apply stored highlight bands (from Redis /{code_id} page).
    highlights = parseHighlights(highlightsStr);
    renderHighlights();

    updateLineNumbers();
    mirrorToHighlight(); // language is set → Prism highlights immediately
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
  renderHighlights();

  const encoded  = window.__ENCODED__  || "";
  const language = window.__LANGUAGE__ || "text";
  const storedHighlights = window.__HIGHLIGHTS__ || "";

  if (encoded.length > 0) {
    // Shared URL: load, highlight with stored language, skip detection entirely
    await loadEncodedSnippet(encoded, language, storedHighlights);
  } else {
    highlights = [];
    renderHighlights();
    codeArea.focus();

    // ── Two-phase inline hint ──────────────────────────────────
    codeArea.addEventListener("input", function showHighlightHint() {
      editorHintEmpty.classList.add("hidden");
      editorHintHighlight.classList.remove("hidden");
    }, { once: true });
  }

  ```
  Logic Flows: ->
  1. Page loads → Show: "Paste or type your code"
  2. User starts typing/pasting → Hide first hint
  3. Code exists → Show: "Select any lines to highlight and share"
  4. Second hint → NEVER hides
  ```
})();