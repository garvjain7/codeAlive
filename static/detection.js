// ── LANGUAGE DETECTION (CodeMirror 6) ────────────────────────────────────────
//
//  State machine:  idle → in-progress → done
//                                     ↘ failed
//
//  The Promise/resolver pattern lets the Create-Link button await the
//  in-flight request without polling, without timers, without races.

import { DEBOUNCE_MS, COOLDOWN_MS, MIN_LINES, MIN_CHARS } from "./constants.js";

// ── Callback registry ─────────────────────────────────────────────────────────

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

  setResult(lang) {
    this.language = lang || "text";
    this.status = "done";
    this._flush(this.language);
    notifyStateChange();
  },

  setFailed() {
    this.language = "text";
    this.status = "failed";
    this._flush("text");
    notifyStateChange();
  },

  reset() {
    this._flush("text");
    this.status = "idle";
    this.language = "text";
    this._resolve = null;
    this._promise = null;
    notifyStateChange();
  },

  softReset() {
    if (this.status === "done" || this.status === "failed") {
      this.status = "idle";
      this.language = "text";
      this._resolve = null;
      this._promise = null;
      notifyStateChange();
    }
  },
};

// ── Threshold check ───────────────────────────────────────────────────────────

export function meetsThreshold(code) {
  return code.split("\n").length >= MIN_LINES || code.length >= MIN_CHARS;
}

// ── Detection trigger ─────────────────────────────────────────────────────────

let lastDetectionCall = 0;

export async function triggerDetection(code, immediate = false) {
  if (!code || !meetsThreshold(code)) return;

  const now = Date.now();
  if (!immediate && now - lastDetectionCall < COOLDOWN_MS) return;
  if (detection.status === "in-progress") return;

  detection.status = "in-progress";
  lastDetectionCall = now;
  notifyStateChange();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);

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

  const lang = data && typeof data.language === "string" ? data.language : "text";
  detection.setResult(lang);
}

// ── Event wiring (Handled by main.js in CM6) ──────────────────────────────────

let debounceTimer = null;

export function clearDetectionDebounce() {
  clearTimeout(debounceTimer);
}

export function handleEditorUpdate(code) {
  detection.softReset();
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    if (detection.status === "idle") {
      triggerDetection(code);
    }
  }, DEBOUNCE_MS);
}

export function handleImmediateDetection(code) {
  detection.reset();
  clearTimeout(debounceTimer);
  triggerDetection(code, true);
}