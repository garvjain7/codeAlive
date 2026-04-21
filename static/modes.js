// ── PAGE MODES (CodeMirror 6) ──────────────────────────────────────────────────
import {
  viewBadge,
  downloadBtn,
  editorHintEmpty,
  editorHintHighlight,
} from "./dom.js";

import { hideShareBar, hideEditWarning, setEditWarningDismissed } from "./ui.js";
import { highlights, renderHighlights, hideHighlightPopup } from "./highlights.js";
import { detection, clearDetectionDebounce } from "./detection.js";

export async function enterViewMode() {
  if (viewBadge) viewBadge.classList.add("show");
  if (downloadBtn) downloadBtn.classList.add("show");
  if (editorHintEmpty) editorHintEmpty.classList.add("hidden");
  if (editorHintHighlight) editorHintHighlight.classList.add("hidden");
}

export async function enterHomeMode() {
  history.pushState({}, "", "/editor");

  const { view } = await import("./dom.js");
  if (view) {
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: "" }
    });
    view.focus();
  }

  hideShareBar();
  if (viewBadge) viewBadge.classList.remove("show");
  if (downloadBtn) downloadBtn.classList.remove("show");

  hideEditWarning();
  setEditWarningDismissed(false);

  clearDetectionDebounce();
  detection.reset();

  highlights.length = 0;
  renderHighlights();
  hideHighlightPopup();
}