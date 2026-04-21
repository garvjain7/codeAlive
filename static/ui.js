// ── UI HELPERS ────────────────────────────────────────────────────────────────
//
//  • Toast notification
//  • Error bar
//  • Language badge
//  • Share bar (show / hide)
//  • Edit warning banner
//
//  ── Dependency rule ──────────────────────────────────────────────────────────
//  This module does NOT import from detection.js, editor.js, or any module
//  that imports from those — preventing circular dependency chains.
//  All data needed for rendering is passed explicitly via function parameters.

import {
  codeArea,
  errorBar,
  toast,
  langDot,
  langBadge,
  shareBar,
  shareUrl,
  editWarning,
  ewDismiss,
} from "./dom.js";

// ── Error bar ─────────────────────────────────────────────────────────────────

export function showError(msg, duration = 4000) {
  errorBar.textContent = msg;
  errorBar.classList.add("visible");
  setTimeout(() => errorBar.classList.remove("visible"), duration);
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let toastTimer;
export function showToast() {
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2000);
}

// ── Language badge ────────────────────────────────────────────────────────────

/**
 * Render the language badge from an explicit state snapshot.
 * Called by main.js whenever detection state changes — never reads
 * the detection object directly so there is no import dependency on detection.js.
 *
 * @param {{ status: string, language: string }} detectionState
 */
export function updateLangBadge({ status, language }) {
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

// ── Share bar ─────────────────────────────────────────────────────────────────

export function showShareBar(url) {
  shareUrl.value = url;
  shareBar.classList.add("visible");
}

export function hideShareBar() {
  shareBar.classList.remove("visible");
}

// ── Edit warning ──────────────────────────────────────────────────────────────

export let editWarningDismissed = false;

export function setEditWarningDismissed(val) {
  editWarningDismissed = val;
}

export function showEditWarning() {
  if (editWarningDismissed) return;
  editWarning.classList.add("show");
}

export function hideEditWarning() {
  editWarning.classList.remove("show");
}

ewDismiss.addEventListener("click", () => {
  editWarningDismissed = true;
  hideEditWarning();
});

codeArea.addEventListener("input", () => {
  if (window.location.pathname !== "/editor") showEditWarning();
});