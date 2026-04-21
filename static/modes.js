// ── PAGE MODES ────────────────────────────────────────────────────────────────
//
//  enterViewMode  — after a snippet is loaded or saved
//  enterHomeMode  — when the user clicks "New" to start fresh

import {
  codeArea,
  viewBadge,
  downloadBtn,
  editorHintEmpty,
  editorHintHighlight,
} from "./dom.js";

import { hideShareBar, hideEditWarning, setEditWarningDismissed } from "./ui.js";
import { highlights, renderHighlights, hideHighlightPopup } from "./highlights.js";
import { detection, clearDetectionDebounce } from "./detection.js";
import { updateLineNumbers } from "./editor.js";

export function enterViewMode() {
  viewBadge.classList.add("show");
  downloadBtn.classList.add("show");
  editorHintEmpty.classList.add("hidden");
  editorHintHighlight.classList.add("hidden");
}

export function enterHomeMode() {
  history.pushState({}, "", "/editor");

  codeArea.value = "";
  codeArea.readOnly = false;

  hideShareBar();
  viewBadge.classList.remove("show");
  downloadBtn.classList.remove("show");

  hideEditWarning();
  setEditWarningDismissed(false);

  // reset() clears detection state, calls mirrorToHighlight() + updateLangBadge()
  clearDetectionDebounce();
  detection.reset();

  // Clear highlights array in-place so all modules see the reset
  highlights.length = 0;
  renderHighlights();
  hideHighlightPopup();

  updateLineNumbers();
  codeArea.focus();
}