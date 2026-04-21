// ── BUTTON HANDLERS ───────────────────────────────────────────────────────────
//
//  • shareBtn       — opens share modal (sections 16)
//  • createShare    — gate + POST /save (section 17)
//  • copyBtn        — copy share URL (section 18)
//  • copyCodeBtn    — copy code (section 18)
//  • newBtn         — enter home mode (section 19)
//  • downloadBtn    — download code as file (section 20)

import {
  codeArea,
  shareBtn,
  createShare,
  copyBtn,
  copyCodeBtn,
  newBtn,
  downloadBtn,
  shareUrl,
  customCode,
} from "./dom.js";

import { MAX_LINES } from "./constants.js";
import { detection, triggerDetection, meetsThreshold } from "./detection.js";
import { highlights, serializeHighlights, hideHighlightPopup } from "./highlights.js";
import { showError, showToast, showShareBar, hideEditWarning, setEditWarningDismissed } from "./ui.js";
import {
  openModal,
  closeModal,
  selectedOption,
  setCreateBtnLoading,
  setCreateBtnNormal,
} from "./modal.js";
import { enterViewMode, enterHomeMode } from "./modes.js";
import { updateLangBadge } from "./ui.js";

// ── 16. SHARE BUTTON ─────────────────────────────────────────────────────────
//
//  Responsibilities (in order):
//    1. Guard: empty editor → show error, return
//    2. Kick off detection if not already running or done
//       a. Meets threshold → triggerDetection(immediate=true)
//       b. Below threshold → commit "text" immediately (no API call needed)
//    3. Open modal — always, regardless of detection state
//
//  The modal's Create Link button handles the wait if detection is mid-flight.

shareBtn.addEventListener("click", () => {
  const code = codeArea.value.trim();

  if (!code) {
    showError("Nothing to share — paste some code first.");
    return;
  }

  if (detection.status === "idle" || detection.status === "failed") {
    if (meetsThreshold(code)) {
      clearTimeout(undefined); // debounceTimer lives in detection.js; paste/typing clear it there
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

// ── 17. CREATE LINK BUTTON (GATE) ────────────────────────────────────────────
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

copyCodeBtn.addEventListener("click", () => {
  const code = codeArea.value;
  if (!code) return;
  navigator.clipboard.writeText(code).then(showToast);
});

// ── 19. NEW SNIPPET ──────────────────────────────────────────────────────────

newBtn.addEventListener("click", () => {
  enterHomeMode();
});

// ── 20. DOWNLOAD ─────────────────────────────────────────────────────────────

downloadBtn.addEventListener("click", () => {
  const code = codeArea.value;
  if (!code) return;

  // Use detected language as file extension, fallback to "txt"
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