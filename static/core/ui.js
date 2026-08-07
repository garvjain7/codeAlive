// ── UI HELPERS (CodeMirror 6) ──────────────────────────────────────────────────
import {
  errorBar,
  toast,
  langDot,
  langBadge,
  shareBar,
  shareUrl,
  editWarning,
  ewDismiss,
} from "./dom.js";

import { translateError } from "./error-service.js";

// ── Error bar ─────────────────────────────────────────────────────────────────

let errorTimer;

export function showError(rawMsgOrErr, options = {}) {
  if (!errorBar) return;

  const duration = typeof options === "number" ? options : (options.duration || 5000);
  const retryFn = typeof options === "object" ? options.retryFn : null;
  const friendlyMsg = translateError(rawMsgOrErr);

  const warningSvg = `<svg class="error-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
    <line x1="12" y1="9" x2="12" y2="13"/>
    <line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>`;

  let html = `${warningSvg}<span class="error-msg-text">${friendlyMsg}</span>`;

  if (retryFn) {
    html += `<button class="error-retry-btn" type="button">Retry</button>`;
  }

  html += `<button class="error-close-btn" type="button" aria-label="Dismiss">&times;</button>`;

  errorBar.innerHTML = html;
  errorBar.classList.add("visible");

  const closeBtn = errorBar.querySelector(".error-close-btn");
  if (closeBtn) {
    closeBtn.onclick = () => hideError();
  }

  const retryBtn = errorBar.querySelector(".error-retry-btn");
  if (retryBtn && retryFn) {
    retryBtn.onclick = () => {
      hideError();
      retryFn();
    };
  }

  clearTimeout(errorTimer);
  if (duration > 0) {
    errorTimer = setTimeout(() => hideError(), duration);
  }
}

export function hideError() {
  if (!errorBar) return;
  errorBar.classList.remove("visible");
  clearTimeout(errorTimer);
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let toastTimer;
export function showToast(msg = "Copied!", duration = 2000) {
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), duration);
}

// ── Language badge ────────────────────────────────────────────────────────────

export function updateLangBadge({ status, language }) {
  if (!langDot || !langBadge) return;
  
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
  if (!shareUrl || !shareBar) return;
  shareUrl.value = url;
  shareBar.classList.add("visible");
}

export function hideShareBar() {
  if (!shareBar) return;
  shareBar.classList.remove("visible");
}

// ── Edit warning ──────────────────────────────────────────────────────────────

export let editWarningDismissed = false;

export function setEditWarningDismissed(val) {
  editWarningDismissed = val;
}

export function showEditWarning() {
  if (editWarningDismissed || !editWarning) return;
  editWarning.classList.add("show");
}

export function hideEditWarning() {
  if (!editWarning) return;
  editWarning.classList.remove("show");
}

if (ewDismiss) {
  ewDismiss.addEventListener("click", () => {
    editWarningDismissed = true;
    hideEditWarning();
  });
}

// ── 11. IMAGE VIEWER MODAL ───────────────────────────────────────────────────

export const imageViewerModal = document.getElementById("image-viewer-modal");
export const imageModalContent = document.getElementById("imageModalContent");
export const imageModalClose = document.getElementById("imageModalClose");

export function showImageModal(url) {
  if (!imageViewerModal || !imageModalContent) return;
  imageModalContent.src = url;
  imageViewerModal.classList.remove("hidden");
}

export function hideImageModal() {
  if (!imageViewerModal) return;
  imageViewerModal.classList.add("hidden");
  imageModalContent.src = "";
}

if (imageModalClose) {
  imageModalClose.addEventListener("click", hideImageModal);
}
if (imageViewerModal) {
  imageViewerModal.addEventListener("click", (e) => {
    // Hide if clicking outside the image itself
    if (e.target === imageViewerModal) hideImageModal();
  });
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && imageViewerModal && !imageViewerModal.classList.contains("hidden")) {
    hideImageModal();
  }
});

import { initTheme, toggleTheme as baseToggle } from "./theme.js";

export function toggleTheme() {
  baseToggle(showToast);
}

// Auto-init theme
initTheme();
