// ── BUTTON HANDLERS (CodeMirror 6) ───────────────────────────────────────────
import {
  shareBtn,
  createShare,
  copyBtn,
  copyCodeBtn,
  newBtn,
  shareUrl,
  customCode,
  searchBtn,
} from "./dom.js";

import { MAX_LINES } from "./constants.js";
import { detection, triggerDetection, meetsThreshold } from "./detection.js";
import { highlights, serializeHighlights, hideHighlightPopup } from "./highlights.js";
import { showError, showToast, showShareBar, hideEditWarning, setEditWarningDismissed, updateLangBadge } from "./ui.js";
import {
  openModal,
  closeModal,
  selectedOption,
  setCreateBtnLoading,
  setCreateBtnNormal,
} from "./modal.js";
import { enterViewMode, enterHomeMode } from "./modes.js";
import { triggerSearch } from "./editor.js";

// ── SEARCH BUTTON ────────────────────────────────────────────────────────────

searchBtn.addEventListener("click", () => {
  triggerSearch();
});

// ── SHARE BUTTON ─────────────────────────────────────────────────────────────

shareBtn.addEventListener("click", async () => {
  const { view } = await import("./dom.js");
  if (!view) return;

  const code = view.state.doc.toString().trim();

  if (!code) {
    showError("Nothing to share — paste some code first.");
    return;
  }

  if (detection.status === "idle" || detection.status === "failed") {
    if (meetsThreshold(code)) {
      triggerDetection(code, /* immediate */ true);
    } else {
      detection.language = "text";
      detection.status   = "done";
      updateLangBadge({ status: detection.status, language: detection.language });
    }
  }

  openModal();
});

// ── 17. CREATE LINK BUTTON (GATE) ────────────────────────────────────────────

createShare.addEventListener("click", async () => {
  const { view } = await import("./dom.js");
  if (!view) return;

  const code = view.state.doc.toString().trim();

  if (!code) {
    showError("Nothing to share.");
    return;
  }

  const lines = view.state.doc.lines;
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

  if (detection.status === "in-progress") {
    setCreateBtnLoading("Language detection in progress…");
    await detection.waitForResult();
  }

  const language = detection.language || "text";

  const formData = new FormData();
  formData.append("code", code);
  formData.append("language", language);
  const highlightsStr = serializeHighlights(highlights);

  formData.append("highlights", highlightsStr || "");
  formData.append("custom_code", custom.trim() || "");

  // Add advanced options if they exist (logged-in users)
  const { snippetPassword, expiryDays, snippetTitle } = await import("./dom.js");
  
  if (snippetTitle) {
    const titleVal = snippetTitle.value.trim();
    if (!titleVal) {
      showError("Please enter a snippet title.");
      return;
    }
    formData.append("title", titleVal);
  }

  if (snippetPassword) {
    formData.append("password", snippetPassword.value || "");
  }
  if (expiryDays) {
    formData.append("expiry", expiryDays.value || "30");
  }

  setCreateBtnLoading("creating...");

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
    hideHighlightPopup();

    hideEditWarning();
    setEditWarningDismissed(false);
  } catch {
    setCreateBtnNormal();
    showError("Network error. Please try again.");
  }
});

// ── 18. COPY ─────────────────────────────────────────────────────────────────

copyBtn.addEventListener("click", () => {
  navigator.clipboard.writeText(shareUrl.value).then(showToast);
});

copyCodeBtn.addEventListener("click", async () => {
  const { view } = await import("./dom.js");
  if (!view) return;

  const code = view.state.doc.toString();
  if (!code) return;
  navigator.clipboard.writeText(code).then(showToast);
});

// ── 19. NEW SNIPPET ──────────────────────────────────────────────────────────

newBtn.addEventListener("click", () => {
  enterHomeMode();
});

// ── 20. DOWNLOAD ─────────────────────────────────────────────────────────────

downloadBtn.addEventListener("click", async () => {
  const { view } = await import("./dom.js");
  if (!view) return;

  const code = view.state.doc.toString();
  if (!code) return;

  const lang =
    detection.language && detection.language !== "text"
      ? detection.language
      : "txt";
  const path = window.location.pathname;
  let slug = "code";
  if (path.startsWith("/s/")) {
    slug = path.split("/").pop();
  } else if (path === "/editor") {
    slug = "new-snippet";
  }

  const blob = new Blob([code], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");

  a.href = url;
  a.download = `${slug}.${lang}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// ── THEME TOGGLE ─────────────────────────────────────────────────────────────
const themeToggleBtn = document.getElementById('themeToggleBtn');
if (themeToggleBtn) {
  themeToggleBtn.addEventListener('click', async () => {
    const { toggleTheme } = await import('./theme.js');
    toggleTheme();
  });
}