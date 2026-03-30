// ── EDITOR BEHAVIOR ───────────────────────────────────────────────────────────
//
//  • Prism mirror overlay (mirrorToHighlight + syncHighlightScroll)
//  • Line numbers + stats (updateLineNumbers)
//  • Scroll synchronisation across all three panels
//  • Tab-key interception
//
//  ── Dependency rule ──────────────────────────────────────────────────────────
//  This module does NOT import from detection.js — preventing circular
//  dependency chains.
//
//  mirrorToHighlight(code, language) receives all data it needs explicitly.
//  The input-event listener needs the current language at fire-time; main.js
//  supplies this via initEditor(getLanguage), where getLanguage is a closure
//  that reads detection.language without this module importing detection.js.

import {
  codeArea,
  lineNums,
  lineInfo,
  charInfo,
  codeHighlight,
  codeHighlighted,
} from "./dom.js";
import { syncHighlightBandsScroll } from "./highlights.js";

// ── Language getter (injected by main.js) ─────────────────────────────────────

/**
 * Returns the current detected language string.
 * Populated by main.js via initEditor() before any events fire.
 *
 * @type {() => string}
 */
let _getLanguage = () => "text";

/**
 * Called once by main.js to inject a getter for the current language.
 * This breaks the circular dependency:
 *   editor.js never imports detection.js — it just calls _getLanguage()
 *   at event-time, which is a closure over detection.language in main.js.
 *
 * @param {() => string} getLanguage
 */
export function initEditor(getLanguage) {
  _getLanguage = getLanguage;
}

// ── Prism mirror ──────────────────────────────────────────────────────────────

/** Safely escape HTML entities for the plain-text fallback. */
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * Re-render the Prism overlay to match the given code + language.
 *
 * Signature uses explicit parameters so callers (main.js, codec.js, tab-key
 * handler) pass exactly what they have — no hidden state reads.
 *
 * Prism.highlight() is wrapped in its own isolated try/catch so that any
 * Prism-internal crash (e.g. tokenizePlaceholders on an unsupported grammar)
 * silently falls back to plain escaped text and never propagates upward.
 *
 * @param {string} code     — text to highlight
 * @param {string} language — Prism language key (e.g. "python", "text")
 */
export function mirrorToHighlight(code, language) {
  console.log("🔥 mirrorToHighlight input:", {
    code,
    language,
  });
  let html;

  if (
    language &&
    language !== "text" &&
    typeof Prism !== "undefined" &&
    Prism.languages[language]
  ) {
    try {
      html = Prism.highlight(code, Prism.languages[language], language);
      console.log(
        "✅ Prism highlighted successfully, lang:",
        language,
        "| output length:",
        html.length,
      );
    } catch (err) {
      console.error(
        "💥 Prism.highlight() threw for lang:",
        language,
        "| error:",
        err,
      );
      html = escapeHtml(code);
    }
  } else {
    // Log exactly WHY we fell into the plain-text path
    if (!language || language === "text") {
      console.log(
        "🔤 mirrorToHighlight: lang is 'text' or empty, using plain text",
      );
    } else if (typeof Prism === "undefined") {
      console.error(
        "❌ mirrorToHighlight: Prism is NOT defined — scripts failed to load",
      );
    } else if (!Prism.languages[language]) {
      console.error(
        "❌ mirrorToHighlight: Prism.languages['" +
          language +
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

export function syncHighlightScroll() {
  codeHighlight.scrollTop = codeArea.scrollTop;
  codeHighlight.scrollLeft = codeArea.scrollLeft;
}

// Re-render overlay on every keystroke.
// _getLanguage() is called at fire-time so it always reflects the latest
// detection result without this module holding a direct reference to detection.
codeArea.addEventListener("input", () => {
  mirrorToHighlight(codeArea.value, _getLanguage());
});

// ── Line numbers ──────────────────────────────────────────────────────────────

export function updateLineNumbers() {
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

// ── Scroll sync ───────────────────────────────────────────────────────────────

// Sync all three scrollable panels together
codeArea.addEventListener("scroll", () => {
  lineNums.scrollTop = codeArea.scrollTop;
  syncHighlightScroll();
  syncHighlightBandsScroll();
});

// ── Tab key ───────────────────────────────────────────────────────────────────

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
  // Pass current values explicitly — no hidden state reads.
  mirrorToHighlight(codeArea.value, _getLanguage());
});
