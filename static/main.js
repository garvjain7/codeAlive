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
  updateLangBadge,
  showError,
  showToast,
} from "./ui.js";
import { 
  loadEncodedSnippet 
} from "./codec.js";
import { 
  initImageHandler, 
  imagePlugin 
} from "./image-handler.js";
import { initUnlock } from "./unlock.js";
import { initEditorFileImport, inferLanguageFromFileName } from "./editor-file-import.js";
import { initBinaryUpload, openBinaryUploadModal } from "./file-upload.js";

import "./ui.js";
import "./modal.js";
import "./actions.js";
import "./theme.js";
import { editorContainer, getView, fileImportBtn } from "./dom.js";

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
  const isViewMode       = window.location.pathname !== "/editor";

  // 2. Initialize CM6
  console.log("Starting CM6 initialization...");
  const view = await createEditor(
    "", // Start empty, will be filled by codec if needed
    language,
    isViewMode
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
  initUnlock();
  initBinaryUpload();
  if (window.__AUTO_OPEN_UPLOAD__) {
    openBinaryUploadModal();
  }

  // 5. Wire Update Listener for Detection
  view.dispatch({
    effects: [
      // We could add the field here if we forgot in editor.js
    ]
  });

  initEditorFileImport({
    button: fileImportBtn,
    onImport: async ({ text, language }) => {
      if (view.state.readOnly) {
        showError("This shared snippet is read-only.");
        return;
      }

      view.dispatch({
        changes: {
          from: 0,
          to: view.state.doc.length,
          insert: text,
        },
      });

      await setLanguage(language);
      view.focus();
      showToast("File imported into the editor.");
    },
    onError: (message) => {
      showError(message);
    },
  });

  // 6. Handle Content Loading
  const importedText = sessionStorage.getItem("imported_text");
  const importedFilename = sessionStorage.getItem("imported_filename");
  if (importedText !== null) {
    sessionStorage.removeItem("imported_text");
    sessionStorage.removeItem("imported_filename");
    view.dispatch({
      changes: {
        from: 0,
        to: view.state.doc.length,
        insert: importedText,
      },
    });
    const detectedLang = inferLanguageFromFileName(importedFilename);
    await setLanguage(detectedLang);
    view.focus();
    showToast("File imported into the editor.");
  } else if (encoded.length > 0 && !window.__IS_PROTECTED__) {
    await loadEncodedSnippet(encoded, language, storedHighlights);
  } else if (!window.__IS_PROTECTED__) {
    // New snippet mode
    view.focus();
  }
  
  // 7. Add Global Listeners
  editorContainer.addEventListener("mouseup", handleTextSelection);
  editorContainer.addEventListener("keyup", (e) => {
    if (e.shiftKey) handleTextSelection();
  });

})();