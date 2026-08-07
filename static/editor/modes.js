// ── PAGE MODES (CodeMirror 6) ──────────────────────────────────────────────────
import {
  viewBadge,
  downloadBtn,
  editorHintEmpty,
  editorHintHighlight,
  shareBtn,
} from "../core/dom.js";

import { hideShareBar, hideEditWarning, setEditWarningDismissed } from "../core/ui.js";
import { highlights, renderHighlights, hideHighlightPopup } from "./highlights.js";
import { detection, clearDetectionDebounce } from "./detection.js";

import { setReadOnly } from "./editor.js";

export async function enterViewMode() {
  if (viewBadge) viewBadge.classList.add("show");
  if (downloadBtn) downloadBtn.classList.add("show");
  if (shareBtn) shareBtn.style.display = "none";
  if (editorHintEmpty) editorHintEmpty.classList.add("hidden");
  if (editorHintHighlight) editorHintHighlight.classList.add("hidden");
  
  // Strictly prohibit editing
  setReadOnly(true);
}

export async function enterHomeMode() {
  history.pushState({}, "", "/editor");

  const { view } = await import("../core/dom.js");
  if (view) {
    // Allow editing in home mode
    setReadOnly(false);
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: "" }
    });
    view.focus();
  }

  hideShareBar();
  if (viewBadge) viewBadge.classList.remove("show");
  if (downloadBtn) downloadBtn.classList.remove("show");
  if (shareBtn) shareBtn.style.display = "";

  hideEditWarning();
  setEditWarningDismissed(false);

  clearDetectionDebounce();
  detection.reset();

  highlights.length = 0;
  renderHighlights();
  hideHighlightPopup();
}
