// ── IMAGE HANDLER ─────────────────────────────────────────────────────────────
//
//  Responsibilities:
//    • Accept image uploads via a toolbar button or drag-and-drop onto codeArea
//    • Validate file type + size (≤ 1MB) client-side before sending
//    • POST to /upload-image → receive image_id
//    • Insert [image:image_id] placeholder at cursor position in the editor
//    • On the viewer side, scan rendered code for [image:image_id] patterns
//      and replace them with a clickable "📎 View Image" element
//    • On click → open /image/{image_id} in a new browser tab

import { codeArea } from "./dom.js";
import { showError } from "./ui.js";
import { updateLineNumbers } from "./editor.js";

// ── Constants ─────────────────────────────────────────────────────────────────

const MAX_UPLOAD_BYTES = 1 * 1024 * 1024; // 1MB — client-side pre-check
const PLACEHOLDER_RE   = /\[image:([a-zA-Z0-9_-]+)\]/g;
const ALLOWED_TYPES    = ["image/jpeg", "image/png", "image/gif", "image/webp"];

// ── Upload button (injected into toolbar by initImageHandler) ─────────────────

let _uploadBtn = null;

// ── Init ──────────────────────────────────────────────────────────────────────

/**
 * Call once from main.js on the editor page (pathname === "/").
 * Wires up the upload button and drag-and-drop.
 */
export function initImageHandler() {
  _uploadBtn = document.getElementById("imageUploadBtn");
  if (!_uploadBtn) return;

  // Hidden file input — triggered by the toolbar button
  const fileInput = document.createElement("input");
  fileInput.type   = "file";
  fileInput.accept = "image/jpeg,image/png,image/gif,image/webp";
  fileInput.style.display = "none";
  document.body.appendChild(fileInput);

  // Toolbar button click → open file picker
  _uploadBtn.addEventListener("click", () => fileInput.click());

  // File selected via picker
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      handleImageFile(fileInput.files[0]);
      fileInput.value = ""; // reset so same file can be re-uploaded
    }
  });

  // ── Drag-and-drop onto codeArea ───────────────────────────────────────────
  codeArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    codeArea.classList.add("drag-over");
  });

  codeArea.addEventListener("dragleave", () => {
    codeArea.classList.remove("drag-over");
  });

  codeArea.addEventListener("drop", (e) => {
    e.preventDefault();
    codeArea.classList.remove("drag-over");

    const files = Array.from(e.dataTransfer.files).filter((f) =>
      ALLOWED_TYPES.includes(f.type),
    );

    if (files.length === 0) {
      showError("Only image files can be dropped here.");
      return;
    }

    // Handle first image only — one at a time
    handleImageFile(files[0]);
  });
}

// ── Handle a selected/dropped file ────────────────────────────────────────────

async function handleImageFile(file) {
  // ── Client-side validation ────────────────────────────────────────────────
  if (!ALLOWED_TYPES.includes(file.type)) {
    showError("Invalid file type. Only JPEG, PNG, GIF and WebP are allowed.");
    return;
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    showError(
      `File too large (${(file.size / 1024).toFixed(0)}KB). Maximum upload size is 1MB.`,
    );
    return;
  }

  // ── Show uploading state on button ────────────────────────────────────────
  setUploadBtnLoading(true);

  try {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/upload-image", {
      method: "POST",
      body:   formData,
    });

    const data = await response.json();

    if (!response.ok) {
      showError(data.detail || "Image upload failed.");
      return;
    }

    // ── Insert placeholder at cursor ──────────────────────────────────────
    insertPlaceholder(data.image_id);

  } catch {
    showError("Network error during image upload. Please try again.");
  } finally {
    setUploadBtnLoading(false);
  }
}

// ── Insert placeholder at cursor position ─────────────────────────────────────

function insertPlaceholder(image_id) {
  const placeholder = `[image:${image_id}]`;
  const start       = codeArea.selectionStart;
  const end         = codeArea.selectionEnd;

  // Insert on its own line for clarity
  const before = codeArea.value.substring(0, start);
  const after  = codeArea.value.substring(end);

  // Wrap in newlines if not already at the start of a line
  const prefix = before.length > 0 && !before.endsWith("\n") ? "\n" : "";
  const suffix = after.length  > 0 && !after.startsWith("\n") ? "\n" : "";

  codeArea.value = before + prefix + placeholder + suffix + after;

  // Move cursor to after the inserted placeholder
  const newPos = start + prefix.length + placeholder.length;
  codeArea.selectionStart = codeArea.selectionEnd = newPos;

  // Trigger line number + mirror updates
  codeArea.dispatchEvent(new Event("input"));
  updateLineNumbers();
}

// ── Upload button loading state ───────────────────────────────────────────────

function setUploadBtnLoading(loading) {
  if (!_uploadBtn) return;
  if (loading) {
    _uploadBtn.disabled     = true;
    _uploadBtn.textContent  = "uploading…";
  } else {
    _uploadBtn.disabled     = false;
    _uploadBtn.textContent  = "📎";
  }
}

// ── Render placeholders in viewer ─────────────────────────────────────────────

/**
 * Scan the Prism-rendered HTML inside #code-highlighted and replace any
 * [image:image_id] text nodes with a clickable "📎 View Image" element.
 *
 * Called from main.js after loadEncodedSnippet completes (view mode only).
 */
export function renderImagePlaceholders() {
  const container = document.getElementById("code-highlighted");
  if (!container) return;

  // Walk all text nodes inside the highlighted code block
  const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    null,
  );

  const replacements = []; // collect first, then replace (avoid live DOM mutation)

  let node;
  while ((node = walker.nextNode())) {
    if (PLACEHOLDER_RE.test(node.textContent)) {
      replacements.push(node);
    }
  }

  replacements.forEach((textNode) => {
    // Reset lastIndex since we're reusing the regex
    PLACEHOLDER_RE.lastIndex = 0;

    const fragment = document.createDocumentFragment();
    let   lastIndex = 0;
    let   match;

    while ((match = PLACEHOLDER_RE.exec(textNode.textContent)) !== null) {
      const image_id = match[1];

      // Text before this match
      if (match.index > lastIndex) {
        fragment.appendChild(
          document.createTextNode(
            textNode.textContent.slice(lastIndex, match.index),
          ),
        );
      }

      // The clickable element
      const btn = document.createElement("span");
      btn.className       = "image-placeholder-btn";
      btn.textContent     = "📎 View Image";
      btn.dataset.imageId = image_id;
      btn.title           = `Click to view image (${image_id})`;
      btn.addEventListener("click", () => openImage(image_id));
      fragment.appendChild(btn);

      lastIndex = match.index + match[0].length;
    }

    // Remaining text after last match
    if (lastIndex < textNode.textContent.length) {
      fragment.appendChild(
        document.createTextNode(textNode.textContent.slice(lastIndex)),
      );
    }

    textNode.parentNode.replaceChild(fragment, textNode);
  });
}

// ── Open image in new tab ─────────────────────────────────────────────────────

function openImage(image_id) {
  window.open(`/image/${image_id}`, "_blank", "noopener,noreferrer");
}