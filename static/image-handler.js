// ── IMAGE HANDLER (CodeMirror 6) ────────────────────────────────────────────────
import {
  WidgetType,
  Decoration,
  ViewPlugin,
  MatchDecorator,
} from "https://esm.sh/@codemirror/view";

import { editorContainer } from "./dom.js";
import { showError } from "./ui.js";

// ── Constants ─────────────────────────────────────────────────────────────────

const MAX_UPLOAD_BYTES = 1 * 1024 * 1024; // 1MB
const ALLOWED_TYPES    = ["image/jpeg", "image/png", "image/gif", "image/webp"];

// ── Image Widget ──────────────────────────────────────────────────────────────

class ImageWidget extends WidgetType {
  constructor(imageId) {
    super();
    this.imageId = imageId;
  }

  eq(other) {
    return other.imageId === this.imageId;
  }

  toDOM() {
    const btn = document.createElement("span");
    btn.className = "image-placeholder-btn";
    btn.textContent = "View Image";
    btn.dataset.imageId = this.imageId;
    btn.title = `Click to view image (${this.imageId})`;
    btn.onclick = () => window.open(`/image/${this.imageId}`, "_blank", "noopener,noreferrer");
    return btn;
  }

  ignoreEvent() {
    return false;
  }
}

const imageMatcher = new MatchDecorator({
  regexp: /\[image:([a-zA-Z0-9_-]+)\]/g,
  decoration: (match) => {
    return Decoration.widget({
      widget: new ImageWidget(match[1]),
      side: 1,
    });
  },
});

export const imagePlugin = ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.decorations = imageMatcher.createDeco(view);
    }
    update(update) {
      this.decorations = imageMatcher.updateDeco(update, this.decorations);
    }
  },
  {
    decorations: (instance) => instance.decorations,
  }
);

// ── Upload logic ──────────────────────────────────────────────────────────────

let _uploadBtn = null;

export function initImageHandler() {
  _uploadBtn = document.getElementById("imageUploadBtn");
  // We might not have a button in the topbar anymore, or it might be elsewhere
  // If it's null, we still want drag-and-drop on the container
  
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = ALLOWED_TYPES.join(",");
  fileInput.style.display = "none";
  document.body.appendChild(fileInput);

  if (_uploadBtn) {
    _uploadBtn.addEventListener("click", () => fileInput.click());
  }

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      handleImageFile(fileInput.files[0]);
      fileInput.value = "";
    }
  });

  // Drag and drop on editor container
  editorContainer.addEventListener("dragover", (e) => {
    e.preventDefault();
    editorContainer.classList.add("drag-over");
  });

  editorContainer.addEventListener("dragleave", () => {
    editorContainer.classList.remove("drag-over");
  });

  editorContainer.addEventListener("drop", (e) => {
    e.preventDefault();
    editorContainer.classList.remove("drag-over");

    const files = Array.from(e.dataTransfer.files).filter((f) =>
      ALLOWED_TYPES.includes(f.type)
    );

    if (files.length === 0) {
      showError("Only image files can be dropped here.");
      return;
    }

    handleImageFile(files[0]);
  });
}

async function handleImageFile(file) {
  if (!ALLOWED_TYPES.includes(file.type)) {
    showError("Invalid file type.");
    return;
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    showError(`File too large (${(file.size / 1024).toFixed(0)}KB). Max 1MB.`);
    return;
  }

  try {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/upload-image", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok) {
      showError(data.detail || "Image upload failed.");
      return;
    }

    insertPlaceholder(data.image_id);
  } catch {
    showError("Network error during image upload.");
  }
}

async function insertPlaceholder(imageId) {
  const { view } = await import("./dom.js");
  if (!view) return;

  const placeholder = `[image:${imageId}]`;
  const { from, to } = view.state.selection.main;
  
  view.dispatch({
    changes: { from, to, insert: placeholder },
    selection: { anchor: from + placeholder.length },
  });
}

// ── Viewer rendering (legacy helper) ──────────────────────────────────────────
export function renderImagePlaceholders() {
  // In CM6, this is handled by the ViewPlugin automatically.
}