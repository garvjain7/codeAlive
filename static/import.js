import { showError } from "./ui.js";

const dataEl = document.getElementById("import-data");
const textEl = document.getElementById("import-preview-text");
if (dataEl) {
  window.__USER_ID__ = dataEl.dataset.userId || "";
  window.__PREVIEW_MODE__ = dataEl.dataset.previewMode || "";
  window.__PREVIEW_URL__ = dataEl.dataset.previewUrl || "";
  window.__PREVIEW_FILENAME__ = dataEl.dataset.previewFilename || "";
  window.__PREVIEW_CONTENT_TYPE__ = dataEl.dataset.previewContentType || "";
  window.__PREVIEW_SIZE__ = Number(dataEl.dataset.previewSize || 0);
  window.__PREVIEW_TEXT__ = textEl ? textEl.textContent : "";
}

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
  if (type.startsWith("audio/") || ext === "mp3") return "audio";
  if (type.startsWith("text/")  || TEXT_ALLOWED_EXTENSIONS.has(ext)) return "text";
  if (type === "application/pdf" || ext === "pdf") return "pdf";
  if (type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" || ext === "docx") return "docx";
  if (type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" || type === "application/vnd.ms-excel" || ["xlsx", "xls"].includes(ext)) return "xlsx";
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

// ── Icon helper ───────────────────────────────────────────────────────────────

function getFileIconSvg(kind) {
  if (kind === "pdf") {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`;
  }
  if (kind === "image") {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`;
  }
  if (kind === "video") {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/></svg>`;
  }
  if (kind === "audio") {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;
  }
  if (kind === "docx" || kind === "xlsx") {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M8 13h8"/><path d="M8 17h8"/></svg>`;
  }
  return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>`;
}

// ── Footer Navigation & Pagination ───────────────────────────────────────────

let pdfDocState = null;
let currentPdfPage = 1;
let currentPdfRenderTask = null;

let xlsxWorkbookState = null;
let currentXlsxSheetIndex = 0;

function updateFooterNavigation(current, total, typeLabel = "Page", customName = null) {
  const footer = document.getElementById("import-preview-footer");
  const indicator = document.getElementById("preview-page-indicator");
  const prevBtn = document.getElementById("preview-prev-btn");
  const nextBtn = document.getElementById("preview-next-btn");

  if (!footer || !indicator || !prevBtn || !nextBtn) return;

  if (total <= 1) {
    footer.classList.add("hidden");
    return;
  }

  footer.classList.remove("hidden");
  const nameStr = customName ? ` (${customName})` : "";
  indicator.textContent = `${typeLabel} ${current} of ${total}${nameStr}`;
  prevBtn.disabled = current <= 1;
  nextBtn.disabled = current >= total;
}

function hideFooterNavigation() {
  const footer = document.getElementById("import-preview-footer");
  if (footer) footer.classList.add("hidden");
}

function toggleFullscreenMode(forceState) {
  if (!previewPanel) return;
  const isCurrentlyFullscreen = previewPanel.classList.contains("is-fullscreen");
  const targetFullscreen = typeof forceState === "boolean"
    ? forceState
    : !isCurrentlyFullscreen;

  if (targetFullscreen) {
    previewPanel.classList.add("is-fullscreen");
  } else {
    previewPanel.classList.remove("is-fullscreen");
  }

  const expandIcon = document.querySelector("#preview-fullscreen-btn .icon-expand");
  const compressIcon = document.querySelector("#preview-fullscreen-btn .icon-compress");
  if (expandIcon && compressIcon) {
    expandIcon.classList.toggle("hidden", targetFullscreen);
    compressIcon.classList.toggle("hidden", !targetFullscreen);
  }

  if (pdfDocState) {
    setTimeout(() => renderPdfPage(currentPdfPage), 60);
  }
}

function initPreviewControls() {
  const prevBtn = document.getElementById("preview-prev-btn");
  const nextBtn = document.getElementById("preview-next-btn");
  const fullscreenBtn = document.getElementById("preview-fullscreen-btn");

  prevBtn?.addEventListener("click", () => {
    if (pdfDocState && currentPdfPage > 1) {
      currentPdfPage--;
      renderPdfPage(currentPdfPage);
    } else if (xlsxWorkbookState && currentXlsxSheetIndex > 0) {
      currentXlsxSheetIndex--;
      renderXlsxSheet(currentXlsxSheetIndex);
    }
  });

  nextBtn?.addEventListener("click", () => {
    if (pdfDocState && currentPdfPage < pdfDocState.numPages) {
      currentPdfPage++;
      renderPdfPage(currentPdfPage);
    } else if (xlsxWorkbookState && currentXlsxSheetIndex < xlsxWorkbookState.SheetNames.length - 1) {
      currentXlsxSheetIndex++;
      renderXlsxSheet(currentXlsxSheetIndex);
    }
  });

  fullscreenBtn?.addEventListener("click", () => toggleFullscreenMode());

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && previewPanel?.classList.contains("is-fullscreen")) {
      toggleFullscreenMode(false);
    }
  });
}

initPreviewControls();

// ── Header Setup ─────────────────────────────────────────────────────────────

function setupPreviewHeader(filename, sizeBytes, contentType, downloadUrl = null, localFile = null) {
  if (!previewTitle || !previewMeta) return;

  const kind = inferPreviewKind(localFile, contentType);
  const iconContainer = document.getElementById("import-preview-icon");
  if (iconContainer) {
    iconContainer.innerHTML = getFileIconSvg(kind);
  }

  previewTitle.textContent = filename || "Preview";

  const size = typeof sizeBytes === "number" && sizeBytes > 0 ? `${Math.round(sizeBytes / 1024)} KB` : "";
  const metaParts = [size, contentType || "application/octet-stream"].filter(Boolean);
  previewMeta.textContent = metaParts.join(" · ");

  const downloadBtn = document.getElementById("preview-download-btn");
  if (downloadBtn) {
    if (downloadUrl) {
      downloadBtn.href = downloadUrl;
      downloadBtn.removeAttribute("download");
      downloadBtn.style.display = "inline-flex";
    } else if (localFile) {
      downloadBtn.href = URL.createObjectURL(localFile);
      downloadBtn.setAttribute("download", localFile.name);
      downloadBtn.style.display = "inline-flex";
    } else {
      downloadBtn.style.display = "none";
    }
  }
}

// ── Render helpers ────────────────────────────────────────────────────────────

async function renderPdfPage(pageNumber) {
  if (!pdfDocState || !previewBody) return;

  if (currentPdfRenderTask) {
    try { currentPdfRenderTask.cancel(); } catch (_) {}
  }

  const page = await pdfDocState.getPage(pageNumber);

  const containerWidth = Math.min(previewBody.clientWidth - 48, 760);
  const unscaledViewport = page.getViewport({ scale: 1.0 });
  const scale = containerWidth > 0 ? (containerWidth / unscaledViewport.width) : 1.2;
  const viewport = page.getViewport({ scale: Math.max(scale, 0.8) });

  let wrapper = previewBody.querySelector(".import-preview-pdf");
  if (!wrapper) {
    clearPreviewBody();
    wrapper = document.createElement("div");
    wrapper.className = "import-preview-pdf";
    previewBody.appendChild(wrapper);
  } else {
    wrapper.innerHTML = "";
  }

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  wrapper.appendChild(canvas);

  currentPdfRenderTask = page.render({ canvasContext: ctx, viewport });
  await currentPdfRenderTask.promise;

  updateFooterNavigation(pageNumber, pdfDocState.numPages, "Page");
}

async function renderPdfPreview(sourceUrl) {
  pdfDocState = null;
  currentPdfPage = 1;
  await loadScript("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js");
  const pdfjsLib = window.pdfjsLib;
  if (!pdfjsLib) throw new Error("PDF.js failed to load");
  pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

  pdfDocState = await pdfjsLib.getDocument(sourceUrl).promise;
  await renderPdfPage(1);
}

async function renderDocxPreview(sourceUrlOrFile) {
  hideFooterNavigation();
  await loadScript("https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.8.0/mammoth.browser.min.js");
  let arrayBuffer;
  if (sourceUrlOrFile instanceof File || sourceUrlOrFile instanceof Blob) {
    arrayBuffer = await sourceUrlOrFile.arrayBuffer();
  } else {
    const resp = await fetch(sourceUrlOrFile);
    arrayBuffer = await resp.arrayBuffer();
  }

  const result = await window.mammoth.convertToHtml({ arrayBuffer });
  clearPreviewBody();
  const wrapper = document.createElement("div");
  wrapper.className = "import-preview-docx";
  wrapper.innerHTML = result.value;
  previewBody.appendChild(wrapper);
}

function renderXlsxSheet(sheetIndex) {
  if (!xlsxWorkbookState || !previewBody) return;
  const sheetName = xlsxWorkbookState.SheetNames[sheetIndex];
  if (!sheetName) return;

  const html = window.XLSX.utils.sheet_to_html(xlsxWorkbookState.Sheets[sheetName], { editable: false });
  clearPreviewBody();
  const wrapper = document.createElement("div");
  wrapper.className = "import-preview-xlsx";
  wrapper.innerHTML = html;
  previewBody.appendChild(wrapper);

  currentXlsxSheetIndex = sheetIndex;
  updateFooterNavigation(sheetIndex + 1, xlsxWorkbookState.SheetNames.length, "Sheet", sheetName);
}

async function renderXlsxPreview(sourceUrlOrFile) {
  xlsxWorkbookState = null;
  currentXlsxSheetIndex = 0;
  await loadScript("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.3/xlsx.full.min.js");
  let arrayBuffer;
  if (sourceUrlOrFile instanceof File || sourceUrlOrFile instanceof Blob) {
    arrayBuffer = await sourceUrlOrFile.arrayBuffer();
  } else {
    const resp = await fetch(sourceUrlOrFile);
    arrayBuffer = await resp.arrayBuffer();
  }

  xlsxWorkbookState = window.XLSX.read(arrayBuffer, { type: "array" });
  renderXlsxSheet(0);
}

// Renders a locally-selected binary file into the preview panel.
async function renderBinaryFileLocally(file) {
  if (!previewPanel || !previewTitle || !previewMeta || !previewBody) return;
  pdfDocState = null;
  xlsxWorkbookState = null;

  const kind = inferPreviewKind(file);
  setupPreviewHeader(file.name, file.size, file.type, null, file);
  clearPreviewBody();
  hideFooterNavigation();
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
      await renderPdfPreview(URL.createObjectURL(file));
      return;
    }
    if (kind === "docx") {
      await renderDocxPreview(file);
      return;
    }
    if (kind === "xlsx") {
      await renderXlsxPreview(file);
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
  pdfDocState = null;
  xlsxWorkbookState = null;

  const kind = inferPreviewKind(null, contentType);
  setupPreviewHeader(filename, sizeBytes, contentType, url, null);
  setPreviewVisible(true);
  clearPreviewBody();
  hideFooterNavigation();

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
    if (kind === "audio") {
      renderAudioPlayer(url, filename);
      return;
    }
    if (kind === "pdf") {
      await renderPdfPreview(url);
      return;
    }
    if (kind === "docx") {
      await renderDocxPreview(url);
      return;
    }
    if (kind === "xlsx") {
      await renderXlsxPreview(url);
      return;
    }
    previewBody.innerHTML = '<div class="import-preview-empty">Preview is not available for this file type yet. Download it instead.</div>';
  } catch (err) {
    previewBody.innerHTML = '<div class="import-preview-empty">Preview could not be generated for this file.</div>';
  }
}

// ── Time formatter ─────────────────────────────────────────────────────────────
function formatAudioTime(seconds) {
  if (isNaN(seconds) || seconds < 0) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
}

// ── Custom Audio player helper ──────────────────────────────────────────────────
function renderAudioPlayer(url, filename) {
  clearPreviewBody();
  previewBody.classList.add("audio-preview-body");

  const playerContainer = document.createElement("div");
  playerContainer.className = "custom-audio-player";

  playerContainer.innerHTML = `
    <audio class="custom-audio-engine" src="${url}" preload="metadata"></audio>
    <div class="cap-top-info">
      <div class="cap-icon-title">
        <span class="cap-music-icon">🎵</span>
        <span class="cap-title"></span>
      </div>
      <div class="cap-time-display">
        <span class="cap-curr-time">0:00</span> / <span class="cap-dur-time">0:00</span>
      </div>
    </div>
    <div class="cap-controls-row">
      <button class="cap-play-btn" type="button" aria-label="Play">
        <svg class="icon-play" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        <svg class="icon-pause hidden" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
      </button>
      <div class="cap-seek-wrap">
        <input type="range" class="cap-seek-slider" min="0" max="100" value="0" step="0.1">
        <div class="cap-seek-progress" style="width: 0%"></div>
      </div>
      <button class="cap-mute-btn" type="button" aria-label="Mute">
        <svg class="icon-vol" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
        <svg class="icon-mute hidden" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>
      </button>
    </div>
  `;

  previewBody.appendChild(playerContainer);

  const titleEl = playerContainer.querySelector(".cap-title");
  titleEl.textContent = filename || "Audio track";

  const audio = playerContainer.querySelector(".custom-audio-engine");
  const playBtn = playerContainer.querySelector(".cap-play-btn");
  const iconPlay = playerContainer.querySelector(".icon-play");
  const iconPause = playerContainer.querySelector(".icon-pause");
  const seekSlider = playerContainer.querySelector(".cap-seek-slider");
  const seekProgress = playerContainer.querySelector(".cap-seek-progress");
  const currTimeEl = playerContainer.querySelector(".cap-curr-time");
  const durTimeEl = playerContainer.querySelector(".cap-dur-time");
  const muteBtn = playerContainer.querySelector(".cap-mute-btn");
  const iconVol = playerContainer.querySelector(".icon-vol");
  const iconMute = playerContainer.querySelector(".icon-mute");

  let isSeeking = false;

  playBtn.addEventListener("click", () => {
    if (audio.paused) {
      audio.play().catch(() => {});
    } else {
      audio.pause();
    }
  });

  audio.addEventListener("play", () => {
    iconPlay.classList.add("hidden");
    iconPause.classList.remove("hidden");
  });

  audio.addEventListener("pause", () => {
    iconPlay.classList.remove("hidden");
    iconPause.classList.add("hidden");
  });

  audio.addEventListener("ended", () => {
    iconPlay.classList.remove("hidden");
    iconPause.classList.add("hidden");
    seekSlider.value = 0;
    seekProgress.style.width = "0%";
    currTimeEl.textContent = "0:00";
  });

  audio.addEventListener("loadedmetadata", () => {
    durTimeEl.textContent = formatAudioTime(audio.duration);
  });

  audio.addEventListener("timeupdate", () => {
    if (!isSeeking && audio.duration) {
      const pct = (audio.currentTime / audio.duration) * 100;
      seekSlider.value = pct;
      seekProgress.style.width = `${pct}%`;
      currTimeEl.textContent = formatAudioTime(audio.currentTime);
    }
  });

  seekSlider.addEventListener("input", () => {
    isSeeking = true;
    const pct = seekSlider.value;
    seekProgress.style.width = `${pct}%`;
    if (audio.duration) {
      currTimeEl.textContent = formatAudioTime((pct / 100) * audio.duration);
    }
  });

  seekSlider.addEventListener("change", () => {
    if (audio.duration) {
      audio.currentTime = (seekSlider.value / 100) * audio.duration;
    }
    isSeeking = false;
  });

  muteBtn.addEventListener("click", () => {
    audio.muted = !audio.muted;
    if (audio.muted) {
      iconVol.classList.add("hidden");
      iconMute.classList.remove("hidden");
    } else {
      iconVol.classList.remove("hidden");
      iconMute.classList.add("hidden");
    }
  });
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

  if (textValidation.error) {
    setStatus(textValidation.error, true);
    return;
  }

  // --- Binary / non-text path ---
  const ext = normalizeExt(file.name);
  if (["zip", "rar", "7z"].includes(ext)) {
    setStatus("Unsupported file type. ZIP files are not supported.", true);
    return;
  }

  const BINARY_RULES = {
    image: { exts: new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]), maxBytes: 500 * 1024 },
    doc: { exts: new Set(["pdf", "docx", "xlsx", "xls"]), maxBytes: 500 * 1024 },
    video: { exts: new Set(["mp4", "webm", "ogg"]), maxBytes: 5 * 1024 * 1024 },
  };

  let matchedCategory = null;
  for (const rule of Object.values(BINARY_RULES)) {
    if (rule.exts.has(ext)) {
      matchedCategory = rule;
      break;
    }
  }

  if (!matchedCategory) {
    setStatus("Unsupported file type. Only text/code files, images, documents, and video files are supported.", true);
    return;
  }

  if (typeof file.size === "number" && file.size > matchedCategory.maxBytes) {
    const limitKb = Math.round(matchedCategory.maxBytes / 1024);
    const limitMb = Math.round(matchedCategory.maxBytes / (1024 * 1024));
    const limitStr = limitMb >= 1 ? `${limitMb}MB` : `${limitKb}KB`;
    setStatus(`File is too large. Maximum allowed size is ${limitStr}.`, true);
    return;
  }

  closeImportModal();
  document.getElementById("import-hero-card")?.classList.add("hidden");
  setStatus("Rendering preview…");
  try {
    await renderBinaryFileLocally(file);
    setStatus("");
    showFilePreviewNavActions(file);
  } catch (err) {
    setStatus("Preview failed: " + (err.message || "unknown error"), true);
  }
});

// ── Reveal navbar actions after a local binary preview ───────────────────────
// The share/preview navbar buttons are rendered by the server only when
// preview_mode === 'share'. For a local preview, we inject them dynamically
// so the user can upload and share if they want to.

// ── Local Unsaved Preview State & Navigation Safeguards ───────────────────────

let currentLocalFile = null;
let isLocalUnsavedPreview = false;

window.addEventListener("beforeunload", (e) => {
  if (isLocalUnsavedPreview) {
    e.preventDefault();
    e.returnValue = "Unsaved File Preview: Your file will be lost if you leave without sharing.";
    return e.returnValue;
  }
});

function showFilePreviewNavActions(file) {
  currentLocalFile = file;
  isLocalUnsavedPreview = true;

  const shareBtn = document.getElementById("file-share-btn");
  const downloadBtn = document.getElementById("file-download-btn");
  const importNewBtn = document.getElementById("file-import-new-btn");

  if (shareBtn) shareBtn.classList.remove("hidden");
  if (downloadBtn) {
    downloadBtn.classList.remove("hidden");
    downloadBtn.href = URL.createObjectURL(file);
    downloadBtn.download = file.name || "download";
  }
  if (importNewBtn) importNewBtn.classList.remove("hidden");
}

// ── "Import New" Button with Unsaved Warning ─────────────────────────────────

const importNewBtn = document.getElementById("file-import-new-btn");
const unsavedModal = document.getElementById("unsaved-modal");
const unsavedCancelBtn = document.getElementById("unsaved-cancel-btn");
const unsavedConfirmBtn = document.getElementById("unsaved-confirm-btn");

if (importNewBtn) {
  importNewBtn.addEventListener("click", () => {
    if (isLocalUnsavedPreview) {
      unsavedModal?.classList.remove("hidden");
    } else {
      window.location.href = "/import";
    }
  });
}

if (unsavedCancelBtn) {
  unsavedCancelBtn.addEventListener("click", () => {
    unsavedModal?.classList.add("hidden");
  });
}

if (unsavedConfirmBtn) {
  unsavedConfirmBtn.addEventListener("click", () => {
    isLocalUnsavedPreview = false;
    currentLocalFile = null;
    unsavedModal?.classList.add("hidden");
    window.location.href = "/import";
  });
}

// ── Share Modal & Custom Slug Logic ───────────────────────────────────────────

const shareModal = document.getElementById("share-modal");
const fileShareBtn = document.getElementById("file-share-btn");
const modalCloseBtn = document.getElementById("modalCloseBtn");
const cancelShare = document.getElementById("cancelShare");
const createShare = document.getElementById("createShare");

const optionRandom = document.getElementById("optionRandom");
const optionCustom = document.getElementById("optionCustom");
const customUrlSection = document.getElementById("customUrlSection");
const customCode = document.getElementById("customCode");
const charCounter = document.getElementById("charCounter");
const urlInputWrap = document.getElementById("urlInputWrap");
const validationIcon = document.getElementById("validationIcon");
const urlHelper = document.getElementById("urlHelper");

let selectedOption = "random";

function selectOption(option) {
  selectedOption = option;
  if (!optionRandom || !optionCustom) return;
  if (option === "random") {
    optionRandom.classList.add("selected");
    optionCustom.classList.remove("selected");
    customUrlSection?.classList.remove("open");
  } else {
    optionCustom.classList.add("selected");
    optionRandom.classList.remove("selected");
    customUrlSection?.classList.add("open");
    setTimeout(() => customCode?.focus(), 80);
  }
}

if (optionRandom) optionRandom.addEventListener("click", () => selectOption("random"));
if (optionCustom) optionCustom.addEventListener("click", () => selectOption("custom"));

function resetModalUI() {
  selectOption("random");
  if (customCode) customCode.value = "";
  if (charCounter) {
    charCounter.textContent = "0/30";
    charCounter.classList.remove("warn", "over");
  }
  if (urlInputWrap) urlInputWrap.classList.remove("valid", "invalid");
  if (validationIcon) {
    validationIcon.textContent = "";
    validationIcon.classList.remove("show", "ok", "err");
  }
  if (urlHelper) {
    urlHelper.textContent = "Letters, numbers and hyphens only";
    urlHelper.classList.remove("error-msg", "ok-msg");
  }
  if (createShare) {
    createShare.disabled = false;
    createShare.innerHTML = "create link →";
  }
}

const VALID_SLUG = /^[a-zA-Z0-9-]+$/;

function validateCustomInput(value) {
  if (!charCounter || !urlInputWrap || !validationIcon || !urlHelper) return;
  const len = value.length;
  charCounter.textContent = `${len}/30`;
  charCounter.classList.toggle("warn", len >= 22 && len < 28);
  charCounter.classList.toggle("over", len >= 28);

  if (len === 0) {
    urlInputWrap.classList.remove("valid", "invalid");
    validationIcon.classList.remove("show", "ok", "err");
    validationIcon.textContent = "";
    urlHelper.textContent = "Letters, numbers and hyphens only";
    urlHelper.classList.remove("error-msg", "ok-msg");
    return;
  }

  const ok = VALID_SLUG.test(value);
  urlInputWrap.classList.toggle("valid", ok);
  urlInputWrap.classList.toggle("invalid", !ok);
  validationIcon.textContent = ok ? "✓" : "✗";
  validationIcon.classList.toggle("ok", ok);
  validationIcon.classList.toggle("err", !ok);
  validationIcon.classList.add("show");
  urlHelper.textContent = ok ? "Looks good!" : "Only letters, numbers and hyphens allowed";
  urlHelper.classList.toggle("ok-msg", ok);
  urlHelper.classList.toggle("error-msg", !ok);
}

if (customCode) {
  customCode.addEventListener("input", () => validateCustomInput(customCode.value));
}

if (fileShareBtn) {
  fileShareBtn.addEventListener("click", () => {
    if (shareModal) {
      shareModal.classList.add("show");
      resetModalUI();
    }
  });
}

function closeShareModal() {
  shareModal?.classList.remove("show");
}

if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeShareModal);
if (cancelShare) cancelShare.addEventListener("click", closeShareModal);
if (shareModal) {
  shareModal.addEventListener("click", (e) => {
    if (e.target === shareModal) closeShareModal();
  });
}

if (createShare) {
  createShare.addEventListener("click", async () => {
    if (!currentLocalFile) {
      showToast("No local file selected to share.");
      return;
    }

    const custom = selectedOption === "custom" ? (customCode?.value || "").trim() : "";
    if (selectedOption === "custom") {
      if (!custom) {
        if (urlHelper) {
          urlHelper.textContent = "Please enter a custom slug";
          urlHelper.classList.add("error-msg");
        }
        return;
      }
      if (!VALID_SLUG.test(custom)) {
        if (urlHelper) {
          urlHelper.textContent = "Only letters, numbers and hyphens allowed";
          urlHelper.classList.add("error-msg");
        }
        return;
      }
    }

    const formData = new FormData();
    formData.append("file", currentLocalFile);
    if (custom) {
      formData.append("custom_code", custom);
    }

    const titleEl = document.getElementById("snippetTitle");
    const passwordEl = document.getElementById("snippetPassword");
    const expiryEl = document.getElementById("expiryDays");

    if (titleEl) {
      const titleVal = titleEl.value.trim();
      if (!titleVal) {
        showError("Please enter a file title.");
        return;
      }
      formData.append("title", titleVal);
    }

    if (passwordEl && passwordEl.value) {
      formData.append("password", passwordEl.value);
    }
    if (expiryEl && expiryEl.value) {
      formData.append("expires_in_days", expiryEl.value);
    }

    createShare.disabled = true;
    createShare.innerHTML = '<span class="btn-spinner"></span>creating link…';

    const performUpload = async () => {
      createShare.disabled = true;
      createShare.innerHTML = '<span class="btn-spinner"></span>creating link…';

      try {
        const response = await fetch("/api/files/upload", {
          method: "POST",
          body: formData,
        });

        const data = await response.json();
        if (!response.ok) {
          createShare.disabled = false;
          createShare.innerHTML = "create link →";
          const errDetail = data.detail || { status: response.status };
          if (urlHelper && selectedOption === "custom" && typeof errDetail === "string") {
            urlHelper.textContent = errDetail;
            urlHelper.classList.add("error-msg");
          } else {
            showError(errDetail, { retryFn: performUpload });
          }
          return;
        }

        isLocalUnsavedPreview = false;
        closeShareModal();
        history.pushState({}, "", data.url);

        if (fileShareBtn) fileShareBtn.classList.add("hidden");
        const downloadBtn = document.getElementById("file-download-btn");
        if (downloadBtn) {
          downloadBtn.href = `/api/files/${data.file_id}`;
          downloadBtn.removeAttribute("download");
        }

        showToast("File shared successfully!");
        navigator.clipboard.writeText(window.location.origin + data.url).catch(() => {});
      } catch (err) {
        createShare.disabled = false;
        createShare.innerHTML = "create link →";
        showError(err, { retryFn: performUpload });
      }
    };

    await performUpload();
  });
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2500);
}
