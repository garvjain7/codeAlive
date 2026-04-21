/* ═══════════════════════════════════════════════════════════════════════════
   CodeAlive — main.js  (entry point + orchestrator)
   ─────────────────────────────────────────────────────────────────────────
   Save flow  : code + detected-language → POST /save → short URL → pushState
   Load flow  : encoded + language (injected by backend) → decompress + render
                + apply Prism highlighting from URL language (no re-detection)
   Detection  : paste → immediate | typing → 1 s debounce | cooldown 2 s
                threshold ≥ 8 lines OR ≥ 100 chars
   Highlight  : Prism.js mirror overlay on top of transparent textarea
   Share gate : Create Link button waits for in-progress detection before /save
   ─────────────────────────────────────────────────────────────────────────
   Architecture — dependency flow (all arrows are import directions):
     dom.js / constants.js  ← imported by everyone, import nothing
     highlights.js          ← dom, constants
     detection.js           ← dom, constants           (NO ui / editor)
     editor.js              ← dom, highlights           (NO detection)
     ui.js                  ← dom                       (NO detection / editor)
     modal.js               ← dom, highlights
     modes.js               ← dom, ui, highlights, detection, editor
     codec.js               ← dom, detection, highlights, editor, ui, modes
     actions.js             ← dom, constants, detection, highlights, ui, modal, modes
     main.js                ← everything (orchestrator — wires the callbacks)
═══════════════════════════════════════════════════════════════════════════ */

// ── Module imports ────────────────────────────────────────────────────────────

import { codeArea, editorHintEmpty, editorHintHighlight } from "./dom.js";

// Side-effect imports: each module wires its own DOM event listeners on load.
import "./highlights.js";
import "./ui.js";
import "./modal.js";
import "./actions.js";

import { detection, initDetection } from "./detection.js";
import { highlights, renderHighlights } from "./highlights.js";
import { initEditor, updateLineNumbers, mirrorToHighlight } from "./editor.js";
import { updateLangBadge } from "./ui.js";
import { loadEncodedSnippet } from "./codec.js";
import { initImageHandler, renderImagePlaceholders } from "./image-handler.js";

// ── Wire detection → ui + editor (the orchestrator's core job) ────────────────
//
//  detection.js is pure state — it calls notifyStateChange() internally but
//  knows nothing about badges or Prism. main.js is the only place that knows
//  about both detection AND the UI/editor modules, so it is the right place
//  to connect them.
//
//  initDetection() registers the callback that detection fires on every
//  state transition (in-progress, done, failed, reset, softReset).
//  The callback receives a plain snapshot { status, language } — not the
//  live detection object — so ui.js and editor.js stay import-free of detection.

initDetection((state) => {
  // 1. Update the language badge for every state change.
  updateLangBadge(state);

  // 2. Re-run Prism only when language resolves or resets — not on every
  //    keystroke (that's handled by editor.js's own input listener).
  //    We pass codeArea.value here so editor.js never needs to read it
  //    from a shared reference.
  mirrorToHighlight(codeArea.value, state.language);
});

// ── Supply a language getter to editor.js ─────────────────────────────────────
//
//  editor.js needs to know the current language when its own input/keydown
//  listeners fire (e.g. Tab key, live typing). We pass a closure that reads
//  detection.language at call-time — editor.js never imports detection.js.

initEditor(() => detection.language);

// ── 21. UNSAVED CHANGES WARNING ───────────────────────────────────────────────

window.addEventListener("beforeunload", (e) => {
  if (window.location.pathname === "/editor" && codeArea.value.trim().length > 0) {
    e.preventDefault();
    e.returnValue = "";
  }
});

// ── 24. INIT ─────────────────────────────────────────────────────────────────

(async function init() {
  updateLineNumbers();
  mirrorToHighlight(codeArea.value, detection.language);
  renderHighlights();

  const encoded          = window.__ENCODED__    || "";
  const language         = window.__LANGUAGE__   || "text";
  const storedHighlights = window.__HIGHLIGHTS__ || "";

  if (encoded.length > 0) {
    await loadEncodedSnippet(encoded, language, storedHighlights);
    renderImagePlaceholders();
  } else {
    highlights.length = 0;
    renderHighlights();
    codeArea.focus();

    initImageHandler();
    // Show highlight hint after first input
    codeArea.addEventListener("input", function showHighlightHint() {
      editorHintEmpty.classList.add("hidden");
      editorHintHighlight.classList.remove("hidden");
    }, { once: true });
  }
})();