// ── CodeAlive — main.js (CM6 Orchestrator) ────────────────────────────────────

import { 
  initEditor, 
  createEditor, 
  setLanguage,
  setReadOnly
} from "./editor.js";
import { 
  detection, 
  initDetection, 
  handleEditorUpdate, 
  handleImmediateDetection 
} from "./detection.js";
import { 
  highlightsField, 
  renderHighlights, 
  initHighlights, 
  handleTextSelection 
} from "./highlights.js";
import { 
  updateLangBadge 
} from "./ui.js";
import { 
  loadEncodedSnippet 
} from "./codec.js";
import { 
  initImageHandler, 
  imagePlugin 
} from "./image-handler.js";

import "./ui.js";
import "./modal.js";
import "./actions.js";
import { editorContainer, getView } from "./dom.js";

// ── Wire detection → ui + editor ─────────────────────────────────────────────

initDetection((state) => {
  updateLangBadge(state);
  // Re-run language swap when detection resolves
  setLanguage(state.language);
});

initEditor(() => detection.language);

// ── 21. UNSAVED CHANGES WARNING ───────────────────────────────────────────────

window.addEventListener("beforeunload", (e) => {
  if (window.location.pathname === "/editor") {
    const view = getView();
    if (view && view.state.doc.length > 0 && !document.getElementById("view-badge").classList.contains("show")) {
      e.preventDefault();
      e.returnValue = "";
    }
  }
});

// ── 24. INIT ─────────────────────────────────────────────────────────────────

(async function init() {
  // 1. Setup Editor
  const encoded          = window.__ENCODED__    || "";
  const language         = window.__LANGUAGE__   || "text";
  const storedHighlights = window.__HIGHLIGHTS__ || "";

  // 2. Initialize CM6
  console.log("Starting CM6 initialization...");
  const view = await createEditor(
    "", // Start empty, will be filled by codec if needed
    language
  );
  console.log("Editor created:", view);

  // 3. Add Feature-specific extensions
  // We add these after creation or during creation in editor.js
  // For simplicity, editor.js already includes highlightsField and imagePlugin?
  // Actually, I should make sure they are in the extensions array.
  
  // Refactor: I'll update editor.js to accept external extensions if needed,
  // but for now I'll just re-dispatch them if I missed them.
  // Better yet, I'll update editor.js right now to include them.

  // 4. Initialize Handlers
  initHighlights();
  initImageHandler();

  // 5. Wire Update Listener for Detection
  view.dispatch({
    effects: [
      // We could add the field here if we forgot in editor.js
    ]
  });

  // 6. Handle Content Loading
  if (encoded.length > 0) {
    await loadEncodedSnippet(encoded, language, storedHighlights);
  } else {
    // New snippet mode
    view.focus();
  }
  
  // 7. Add Global Listeners
  editorContainer.addEventListener("mouseup", handleTextSelection);
  editorContainer.addEventListener("keyup", (e) => {
    if (e.shiftKey) handleTextSelection();
  });

})();