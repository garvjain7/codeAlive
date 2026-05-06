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

// ── Error bar ─────────────────────────────────────────────────────────────────

export function showError(msg, duration = 4000) {
  if (!errorBar) return;
  errorBar.textContent = msg;
  errorBar.classList.add("visible");
  setTimeout(() => errorBar.classList.remove("visible"), duration);
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