// ── LANGUAGE DETECTION ────────────────────────────────────────────────────────
//
//  State machine:  idle → in-progress → done
//                                     ↘ failed
//
//  The Promise/resolver pattern lets the Create-Link button await the
//  in-flight request without polling, without timers, without races.
//
//  ── Dependency rule ──────────────────────────────────────────────────────────
//  This module is intentionally self-contained:
//    • NO imports from ui.js or editor.js (prevents circular dependencies)
//    • UI/editor reactions are triggered via the onStateChange callback,
//      which is injected by main.js at startup via initDetection().
//    • This module only imports from dom.js and constants.js.

import { codeArea } from "./dom.js";
import { DEBOUNCE_MS, COOLDOWN_MS, MIN_LINES, MIN_CHARS } from "./constants.js";

// ── Callback registry ─────────────────────────────────────────────────────────
//
//  Instead of importing updateLangBadge / mirrorToHighlight directly (which
//  would create a cycle), detection calls a single onStateChange() hook.
//  main.js registers the hook via initDetection() before anything else runs.
//
//  The hook receives the current detection state snapshot so callers never
//  need to import the detection object itself to read its state.

/** @type {((state: { status: string, language: string }) => void) | null} */
let _onStateChange = null;

/**
 * Register the state-change callback.
 * Must be called once by main.js before any detection can fire.
 *
 * @param {(state: { status: string, language: string }) => void} cb
 */
export function initDetection(cb) {
  _onStateChange = cb;
}

/** Fire the callback with a plain snapshot — never the live object. */
function notifyStateChange() {
  if (_onStateChange) {
    _onStateChange({ status: detection.status, language: detection.language });
  }
}

// ── State machine ─────────────────────────────────────────────────────────────

export const detection = {
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
    notifyStateChange(); // replaces: updateLangBadge() + mirrorToHighlight()
  },

  /** Called on network error or timeout. */
  setFailed() {
    this.language = "text";
    this.status = "failed";
    this._flush("text");
    notifyStateChange(); // replaces: updateLangBadge()
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
    notifyStateChange(); // replaces: updateLangBadge() + mirrorToHighlight()
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
      notifyStateChange(); // replaces: updateLangBadge()
    }
  },
};

// ── Threshold check ───────────────────────────────────────────────────────────

/** Returns true if code is long enough to bother sending to the detector. */
export function meetsThreshold(code) {
  return code.split("\n").length >= MIN_LINES || code.length >= MIN_CHARS;
}

// ── Detection trigger ─────────────────────────────────────────────────────────

let lastDetectionCall = 0;

/**
 * POST /detect-language and update detection state.
 *
 * try/catch scope is intentionally narrow — it only guards the fetch and
 * the JSON parse. detection.setResult() is called OUTSIDE the try block
 * so that a Prism crash inside the onStateChange callback can never
 * be mistaken for a network failure and trigger setFailed().
 *
 * @param {string}  code      — current editor content
 * @param {boolean} immediate — if true, bypass the cooldown guard
 */
export async function triggerDetection(code, immediate = false) {
  if (!code || !meetsThreshold(code)) return;

  const now = Date.now();
  if (!immediate && now - lastDetectionCall < COOLDOWN_MS) return;
  if (detection.status === "in-progress") return;

  detection.status = "in-progress";
  lastDetectionCall = now;
  notifyStateChange(); // badge shows "detecting…"

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

// ── Event wiring ──────────────────────────────────────────────────────────────

let debounceTimer = null;

/** Export so modes.js / actions.js can clear the debounce on reset. */
export function clearDetectionDebounce() {
  clearTimeout(debounceTimer);
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