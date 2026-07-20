// ── Inlined helpers from editor-file-import.js ───────────────────────────────
// (Avoids the ES module import statement that caused SyntaxError on the /import page)

const MAX_TEXT_IMPORT_BYTES = 1024 * 1024;

const TEXT_ALLOWED_EXTENSIONS = new Set([
  "txt", "md", "markdown", "json", "csv", "py", "js", "jsx", "ts", "tsx",
  "css", "html", "xml", "yaml", "yml", "toml", "sql", "c", "cc", "cpp", "cs",
  "go", "java", "php", "rb", "rs", "swift", "kt", "scala", "sh", "bash",
  "ps1", "dockerfile", "lua", "r", "dart", "perl", "pl", "vue", "svelte",
]);

function normalizeExt(fileName) {
  if (!fileName) return "";
  const parts = fileName.split(".");
  if (parts.length < 2) return "";
  return parts[parts.length - 1].toLowerCase();
}

function validateImportedTextFile(file) {
  if (!file || typeof file !== "object") return { ok: false, error: "Please choose a file first." };
  if (!file.name) return { ok: false, error: "The selected file does not have a valid name." };
  const ext = normalizeExt(file.name);
  if (!ext || !TEXT_ALLOWED_EXTENSIONS.has(ext)) return { ok: false };
  if (typeof file.size === "number" && file.size > MAX_TEXT_IMPORT_BYTES) {
    return { ok: false, error: `File is too large. Maximum allowed size is ${Math.round(MAX_TEXT_IMPORT_BYTES / 1024 / 1024)}MB.` };
  }
  return { ok: true, extension: ext };
}

function readTextFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Unable to read the selected file."));
    reader.readAsText(file, "utf-8");
  });
}

// ── DOM refs ─────────────────────────────────────────────────────────────────

const statusBox     = document.getElementById("import-status");
const form          = document.getElementById("import-form");
const fileInput     = document.getElementById("import-file-input");
const submitButton  = document.getElementById("import-submit");
const dropzone      = document.getElementById("import-dropzone");
const modalOverlay  = document.getElementById("import-modal-overlay");
const openModalButton  = document.getElementById("open-import-modal");
const closeModalButton = document.getElementById("import-modal-close");
const previewPanel  = document.getElementById("import-preview");
const previewTitle  = document.getElementById("import-preview-title");
const previewMeta   = document.getElementById("import-preview-meta");
const previewBody   = document.getElementById("import-preview-body");
const dropzonePrompt   = document.getElementById("dropzone-prompt");
const dropzoneFileInfo = document.getElementById("dropzone-file-info");
const selectedFilename = document.getElementById("selected-filename");

// ── Utilities ─────────────────────────────────────────────────────────────────

function setStatus(message, isError = false) {
  if (!statusBox) return;
  statusBox.textContent = message || "";
  statusBox.style.color = isError ? "#fda4af" : "#cbd5e1";
}

function formatPreviewMeta(filename, sizeBytes, contentType) {
  const size = typeof sizeBytes === "number" && sizeBytes > 0 ? `${Math.round(sizeBytes / 1024)} KB` : "";
  return [filename, size, contentType].filter(Boolean).join(" • ");
}

function clearPreviewBody() {
  if (previewBody) previewBody.innerHTML = "";
}

function setPreviewVisible(visible) {
  previewPanel?.classList.toggle("hidden", !visible);
}

function inferPreviewKind(file, contentType) {
  const type = ((file && file.type) || contentType || "").toLowerCase();
  const name = ((file && file.name) || "").toLowerCase();
  const ext  = name.split(".").pop() || "";

  if (type.startsWith("image/") || ["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) return "image";
  if (type.startsWith("video/") || ["mp4", "webm", "ogg"].includes(ext)) return "video";
  if (type.startsWith("text/")  || TEXT_ALLOWED_EXTENSIONS.has(ext)) return "text";
  if (type === "application/pdf" || ext === "pdf") return "pdf";
  if (type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" || ext === "docx") return "docx";
  if (type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" || ext === "xlsx") return "xlsx";
  return "binary";
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === "true") return resolve();
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error(`Unable to load ${src}`)), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.addEventListener("load", () => { script.dataset.loaded = "true"; resolve(); }, { once: true });
    script.addEventListener("error", () => reject(new Error(`Unable to load ${src}`)), { once: true });
    document.head.appendChild(script);
  });
}

// ── Render helpers ────────────────────────────────────────────────────────────

async function renderPdfPreview(sourceUrl, container) {
  await loadScript("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js");
  const pdfjsLib = window.pdfjsLib;
  if (!pdfjsLib) throw new Error("PDF.js failed to load");
  pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  const pdf = await pdfjsLib.getDocument(sourceUrl).promise;
  const wrapper = document.createElement("div");
  wrapper.className = "import-preview-pdf";
  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const viewport = page.getViewport({ scale: 1.1 });
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    canvas.width  = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvasContext: ctx, viewport }).promise;
    wrapper.appendChild(canvas);
  }
  container.appendChild(wrapper);
}

async function renderDocxPreview(file, container) {
  await loadScript("https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.8.0/mammoth.browser.min.js");
  const arrayBuffer = await file.arrayBuffer();
  const result = await window.mammoth.convertToHtml({ arrayBuffer });
  const wrapper = document.createElement("div");
  wrapper.className = "import-preview-docx";
  wrapper.innerHTML = result.value;
  container.appendChild(wrapper);
}

async function renderXlsxPreview(file, container) {
  await loadScript("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.3/xlsx.full.min.js");
  const arrayBuffer = await file.arrayBuffer();
  const workbook = window.XLSX.read(arrayBuffer, { type: "array" });
  const firstSheet = workbook.SheetNames[0];
  const html = window.XLSX.utils.sheet_to_html(workbook.Sheets[firstSheet], { editable: false });
  const wrapper = document.createElement("div");
  wrapper.className = "import-preview-xlsx";
  wrapper.innerHTML = html;
  container.appendChild(wrapper);
}

// Renders a locally-selected binary file into the existing preview panel on the page.
// No upload or share call is made here.
async function renderBinaryFileLocally(file) {
  if (!previewPanel || !previewTitle || !previewMeta || !previewBody) return;
  const kind = inferPreviewKind(file);
  previewTitle.textContent = file.name || "Preview";
  previewMeta.textContent  = formatPreviewMeta(file.name, file.size, file.type);
  clearPreviewBody();
  setPreviewVisible(true);

  try {
    if (kind === "image") {
      const img = document.createElement("img");
      img.src = URL.createObjectURL(file);
      img.alt = file.name;
      previewBody.appendChild(img);
      return;
    }
    if (kind === "video") {
      const video = document.createElement("video");
      video.src = URL.createObjectURL(file);
      video.controls = true;
      video.autoplay = false;
      previewBody.appendChild(video);
      return;
    }
    if (kind === "pdf") {
      await renderPdfPreview(URL.createObjectURL(file), previewBody);
      return;
    }
    if (kind === "docx") {
      await renderDocxPreview(file, previewBody);
      return;
    }
    if (kind === "xlsx") {
      await renderXlsxPreview(file, previewBody);
      return;
    }
    previewBody.innerHTML = '<div class="import-preview-empty">Preview is not available for this file type.</div>';
  } catch (err) {
    previewBody.innerHTML = '<div class="import-preview-empty">Preview could not be generated for this file.</div>';
  }
}

// Renders a remotely-served shared file (preview_mode === 'share') into the preview panel.
async function renderPreviewForSharedFile({ url, contentType, filename, sizeBytes, text }) {
  if (!previewPanel || !previewTitle || !previewMeta || !previewBody) return;
  previewTitle.textContent = filename || "Preview";
  previewMeta.textContent  = formatPreviewMeta(filename, sizeBytes, contentType);
  setPreviewVisible(true);
  clearPreviewBody();

  const kind = inferPreviewKind(null, contentType);
  try {
    if (kind === "text") {
      const pre = document.createElement("pre");
      pre.textContent = text || "";
      previewBody.appendChild(pre);
      return;
    }
    if (kind === "image") {
      const img = document.createElement("img");
      img.src = url;
      img.alt = filename;
      previewBody.appendChild(img);
      return;
    }
    if (kind === "video") {
      const video = document.createElement("video");
      video.src = url;
      video.controls = true;
      previewBody.appendChild(video);
      return;
    }
    if (kind === "pdf") {
      await renderPdfPreview(url, previewBody);
      return;
    }
    if (kind === "docx") {
      const resp = await fetch(url);
      const ab   = await resp.arrayBuffer();
      await loadScript("https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.8.0/mammoth.browser.min.js");
      const result  = await window.mammoth.convertToHtml({ arrayBuffer: ab });
      const wrapper = document.createElement("div");
      wrapper.className = "import-preview-docx";
      wrapper.innerHTML = result.value;
      previewBody.appendChild(wrapper);
      return;
    }
    if (kind === "xlsx") {
      const resp = await fetch(url);
      const ab   = await resp.arrayBuffer();
      await loadScript("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.3/xlsx.full.min.js");
      const workbook   = window.XLSX.read(ab, { type: "array" });
      const firstSheet = workbook.SheetNames[0];
      const html       = window.XLSX.utils.sheet_to_html(workbook.Sheets[firstSheet], { editable: false });
      const wrapper    = document.createElement("div");
      wrapper.className = "import-preview-xlsx";
      wrapper.innerHTML = html;
      previewBody.appendChild(wrapper);
      return;
    }
    previewBody.innerHTML = '<div class="import-preview-empty">Preview is not available for this file type yet. Download it instead.</div>';
  } catch (err) {
    previewBody.innerHTML = '<div class="import-preview-empty">Preview could not be generated for this file.</div>';
  }
}

// ── Modal open / close ────────────────────────────────────────────────────────

function openImportModal() {
  modalOverlay?.classList.remove("hidden");
  modalOverlay?.setAttribute("aria-hidden", "false");
}

function closeImportModal() {
  modalOverlay?.classList.add("hidden");
  modalOverlay?.setAttribute("aria-hidden", "true");
}

openModalButton?.addEventListener("click", openImportModal);
closeModalButton?.addEventListener("click", closeImportModal);
modalOverlay?.addEventListener("click", (event) => {
  if (event.target === modalOverlay) closeImportModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && modalOverlay && !modalOverlay.classList.contains("hidden")) {
    closeImportModal();
  }
});

// Auto-open modal when we are NOT in share-preview mode
if (window.__PREVIEW_MODE__ !== "share") {
  openImportModal();
}

// ── Drag-and-drop ─────────────────────────────────────────────────────────────

dropzone?.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.style.borderColor = "rgba(63,224,160,0.8)";
  dropzone.style.transform   = "translateY(-1px)";
});

dropzone?.addEventListener("dragleave", () => {
  dropzone.style.borderColor = "rgba(63,224,160,0.4)";
  dropzone.style.transform   = "none";
});

function updateSelectedFileDisplay(file) {
  if (file) {
    dropzonePrompt?.classList.add("hidden");
    dropzoneFileInfo?.classList.remove("hidden");
    if (selectedFilename) {
      selectedFilename.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
    }
    setStatus(`Selected: ${file.name}`);
  } else {
    dropzonePrompt?.classList.remove("hidden");
    dropzoneFileInfo?.classList.add("hidden");
    if (selectedFilename) selectedFilename.textContent = "";
    setStatus("");
  }
}

dropzone?.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.style.borderColor = "rgba(63,224,160,0.4)";
  dropzone.style.transform   = "none";
  const [file] = event.dataTransfer?.files || [];
  if (fileInput && file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    updateSelectedFileDisplay(file);
  }
});

fileInput?.addEventListener("change", () => {
  const [file] = fileInput.files || [];
  updateSelectedFileDisplay(file || null);
});

// ── Share-preview mode: render the already-uploaded shared file ───────────────

if (window.__PREVIEW_MODE__ === "share" && window.__PREVIEW_URL__) {
  window.addEventListener("load", () => {
    renderPreviewForSharedFile({
      url:         window.__PREVIEW_URL__,
      contentType: window.__PREVIEW_CONTENT_TYPE__,
      filename:    window.__PREVIEW_FILENAME__,
      sizeBytes:   window.__PREVIEW_SIZE__,
      text:        window.__PREVIEW_TEXT__,
    });
  });
}

// ── Import button handler ─────────────────────────────────────────────────────

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const [file] = fileInput?.files || [];
  if (!file) {
    setStatus("Choose a file before importing.", true);
    return;
  }

  // --- Text / code path ---
  // If the extension is a recognized text/code type, read locally and inject
  // directly into the editor via sessionStorage → /editor redirect.
  // No upload, no share call.
  const textValidation = validateImportedTextFile(file);
  if (textValidation.ok) {
    submitButton.disabled = true;
    setStatus("Reading file…");
    try {
      const text = await readTextFile(file);
      sessionStorage.setItem("imported_text",     text);
      sessionStorage.setItem("imported_filename", file.name);
      window.location.href = "/editor";
    } catch (err) {
      setStatus(err.message || "Failed to read text file.", true);
      submitButton.disabled = false;
    }
    return;
  }

  // --- Binary / non-text path ---
  // Render locally into the existing full-screen preview panel on the page.
  // No upload, no share/save call at this stage.
  // User can share afterward using the Share button that appears in the navbar
  // when the preview panel is visible.
  closeImportModal();
  setStatus("Rendering preview…");
  try {
    await renderBinaryFileLocally(file);
    setStatus("");
    // Reveal the Share + Download navbar actions
    showFilePreviewNavActions(file);
  } catch (err) {
    setStatus("Preview failed: " + (err.message || "unknown error"), true);
  }
});

// ── Reveal navbar actions after a local binary preview ───────────────────────
// The share/preview navbar buttons are rendered by the server only when
// preview_mode === 'share'. For a local preview, we inject them dynamically
// so the user can upload and share if they want to.

function showFilePreviewNavActions(file) {
  // Nothing to do here — the existing share flow is on the editor page for
  // text files; for binary files the user can decide whether to upload later.
  // We intentionally do NOT call any save/share endpoint here.
}

// ── Share-link copy (navbar Share button, visible in share-preview mode) ──────

const shareBtn = document.getElementById("file-share-btn");
if (shareBtn) {
  shareBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      showToast("Link copied to clipboard!");
    } catch (err) {
      alert("Failed to copy link.");
    }
  });
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
}
