/* ─────────────────────────────────────────────────────────
   CodeAlive — main.js
   Save flow  : code → POST /save → short URL → pushState
   Load flow  : encoded (injected by backend) → base64 decode
                → gzip decompress → render in editor
───────────────────────────────────────────────────────── */

const codeArea  = document.getElementById("codeArea");
const lineNums  = document.getElementById("line-numbers");
const lineInfo  = document.getElementById("lineInfo");
const charInfo  = document.getElementById("charInfo");

const shareBtn  = document.getElementById("shareBtn");
const newBtn    = document.getElementById("newBtn");

const shareBar  = document.getElementById("share-bar");
const shareUrl  = document.getElementById("shareUrl");
const copyBtn   = document.getElementById("copyBtn");

const errorBar  = document.getElementById("error-bar");
const toast     = document.getElementById("toast");
const viewBadge = document.getElementById("view-badge");

/* Share modal elements */
const shareModal  = document.getElementById("share-modal");
const createShare = document.getElementById("createShare");
const cancelShare = document.getElementById("cancelShare");
const customCode  = document.getElementById("customCode");

const MAX_LINES = 1000;

/* ── Line numbers ───────────────────────────────────────── */

function updateLineNumbers() {

  const lines     = codeArea.value.split("\n");
  const count     = lines.length;
  const cursorPos = codeArea.selectionStart;
  const activeLine = codeArea.value.substring(0, cursorPos).split("\n").length;

  lineInfo.textContent = `${count} line${count !== 1 ? "s" : ""}`;
  charInfo.textContent = `${codeArea.value.length} chars`;

  lineNums.innerHTML = lines
    .map((_, i) => `<span class="${i + 1 === activeLine ? "active" : ""}">${i + 1}</span>`)
    .join("");

  lineNums.scrollTop = codeArea.scrollTop;
}

codeArea.addEventListener("input", updateLineNumbers);
codeArea.addEventListener("keyup", updateLineNumbers);
codeArea.addEventListener("click", updateLineNumbers);

codeArea.addEventListener("scroll", () => {
  lineNums.scrollTop = codeArea.scrollTop;
});

/* Tab support */

codeArea.addEventListener("keydown", (e) => {

  if (e.key === "Tab") {

    e.preventDefault();

    const start = codeArea.selectionStart;
    const end   = codeArea.selectionEnd;

    codeArea.value =
      codeArea.value.substring(0, start) +
      "  " +
      codeArea.value.substring(end);

    codeArea.selectionStart = codeArea.selectionEnd = start + 2;

    updateLineNumbers();
  }
});

/* ── Error / toast helpers ───────────────────────────────── */

function showError(msg, duration = 4000) {

  errorBar.textContent = msg;
  errorBar.classList.add("visible");

  setTimeout(() => {
    errorBar.classList.remove("visible");
  }, duration);
}

let toastTimer;

function showToast() {

  toast.classList.add("show");

  clearTimeout(toastTimer);

  toastTimer = setTimeout(() => {
    toast.classList.remove("show");
  }, 2000);
}

/* ── Share bar ───────────────────────────────────────────── */

function showShareBar(url) {

  shareUrl.value = url;
  shareBar.classList.add("visible");
}

function hideShareBar() {

  shareBar.classList.remove("visible");
}

/* ── Share modal open ───────────────────────────────────── */

shareBtn.addEventListener("click", () => {

  const code = codeArea.value.trim();

  if (!code) {
    showError("Nothing to share — paste some code first.");
    return;
  }

  shareModal.classList.add("show");

  customCode.value = "";
  customCode.focus();
});

/* Cancel modal */

cancelShare.addEventListener("click", () => {

  shareModal.classList.remove("show");
});

/* ── Create Share Link ───────────────────────────────────── */

createShare.addEventListener("click", async () => {

  const code = codeArea.value.trim();

  if (!code) {
    showError("Nothing to share.");
    return;
  }

  const lines = code.split("\n").length;

  if (lines > MAX_LINES) {
    showError(`Too long: ${lines} lines. Max is ${MAX_LINES}.`);
    return;
  }

  let custom = customCode.value;

  if (custom.endsWith(" ")) {
    showError("Custom code cannot end with space.");
    return;
  }

  if (custom.length > 30) {
    showError("Custom code too long (max 30 characters).");
    return;
  }

  const formData = new FormData();

  formData.append("code", code);

  if (custom.trim() !== "") {
    formData.append("custom_code", custom.trim());
  }

  try {

    const response = await fetch("/save", {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      showError(data.detail || "Failed to save.");
      return;
    }

    const fullUrl = window.location.origin + data.url;

    history.pushState({}, "", data.url);

    showShareBar(fullUrl);

    enterViewMode();

    shareModal.classList.remove("show");

  } catch (err) {

    showError("Network error. Please try again.");
  }
});

/* ── Copy ───────────────────────────────────────────────── */

copyBtn.addEventListener("click", () => {

  navigator.clipboard.writeText(shareUrl.value).then(() => {

    showToast();
  });
});

/* ── New snippet ────────────────────────────────────────── */

newBtn.addEventListener("click", () => {

  history.pushState({}, "", "/");

  codeArea.value = "";
  codeArea.readOnly = false;

  hideShareBar();

  viewBadge.classList.remove("show");

  updateLineNumbers();

  codeArea.focus();
});

/* ── View mode ──────────────────────────────────────────── */

function enterViewMode() {

  viewBadge.classList.add("show");
}

/* ── Decode + decompress ───────────────────────────────── */

async function decodeAndDecompress(encoded) {

  const std = encoded.replace(/-/g, "+").replace(/_/g, "/");
  const padded = std + "=".repeat((4 - (std.length % 4)) % 4);

  const binary = atob(padded);

  const bytes = new Uint8Array(binary.length);

  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }

  const ds = new DecompressionStream("gzip");

  const writer = ds.writable.getWriter();

  writer.write(bytes);
  writer.close();

  const reader = ds.readable.getReader();

  const chunks = [];

  while (true) {

    const { done, value } = await reader.read();

    if (done) break;

    chunks.push(value);
  }

  const total = chunks.reduce((sum, c) => sum + c.length, 0);

  const result = new Uint8Array(total);

  let offset = 0;

  for (const chunk of chunks) {

    result.set(chunk, offset);

    offset += chunk.length;
  }

  return new TextDecoder().decode(result);
}

/* ── Load encoded snippet ───────────────────────────────── */

async function loadEncodedSnippet(encoded) {

  try {

    const code = await decodeAndDecompress(encoded);

    codeArea.value = code;

    codeArea.readOnly = false;

    updateLineNumbers();

    showShareBar(window.location.href);

    enterViewMode();

  } catch (err) {

    showError("Failed to decode snippet.");

    console.error(err);
  }
}

/* ── Init ───────────────────────────────────────────────── */

(async function init() {

  updateLineNumbers();

  const encoded = window.__ENCODED__;

  if (encoded && encoded.length > 0) {

    await loadEncodedSnippet(encoded);

  } else {

    codeArea.focus();
  }

})();