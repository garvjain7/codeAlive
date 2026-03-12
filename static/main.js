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

const shareBtn   = document.getElementById("shareBtn");
const newBtn     = document.getElementById("newBtn");
const downloadBtn = document.getElementById("downloadBtn");

const shareBar  = document.getElementById("share-bar");
const shareUrl  = document.getElementById("shareUrl");
const copyBtn   = document.getElementById("copyBtn");

const errorBar  = document.getElementById("error-bar");
const toast     = document.getElementById("toast");
const viewBadge = document.getElementById("view-badge");

/* Share modal elements */
const shareModal       = document.getElementById("share-modal");
const createShare      = document.getElementById("createShare");
const cancelShare      = document.getElementById("cancelShare");
const modalCloseBtn    = document.getElementById("modalCloseBtn");
const customCode       = document.getElementById("customCode");
const charCounter      = document.getElementById("charCounter");
const urlInputWrap     = document.getElementById("urlInputWrap");
const validationIcon   = document.getElementById("validationIcon");
const urlHelper        = document.getElementById("urlHelper");
const customUrlSection = document.getElementById("customUrlSection");
const optionRandom     = document.getElementById("optionRandom");
const optionCustom     = document.getElementById("optionCustom");

const MAX_LINES = 1000;

const editWarning = document.getElementById("edit-warning");
const ewDismiss   = document.getElementById("ewDismiss");

/* Track whether the warning has been dismissed this session */
let editWarningDismissed = false;

function showEditWarning() {
  if (editWarningDismissed) return;
  editWarning.classList.add("show");
}

function hideEditWarning() {
  editWarning.classList.remove("show");
}

ewDismiss.addEventListener("click", () => {
  editWarningDismissed = true;
  hideEditWarning();
});

/* Show warning when user edits while on a shared URL (not '/') */
codeArea.addEventListener("input", () => {
  if (window.location.pathname !== "/") {
    showEditWarning();
  }
});

/* ── Line numbers ───────────────────────────────────────── */

function updateLineNumbers() {

  const lines      = codeArea.value.split("\n");
  const count      = lines.length;
  const cursorPos  = codeArea.selectionStart;
  const activeLine = codeArea.value.substring(0, cursorPos).split("\n").length;

  lineInfo.textContent = `${count} line${count !== 1 ? "s" : ""}`;
  charInfo.textContent = `${codeArea.value.length} chars`;

  lineNums.innerHTML = lines
    .map((_, i) => `<span class="${i + 1 === activeLine ? "active" : ""}">${i + 1}</span>`)
    .join("");

  lineNums.scrollTop = codeArea.scrollTop;
}

codeArea.addEventListener("input",  updateLineNumbers);
codeArea.addEventListener("keyup",  updateLineNumbers);
codeArea.addEventListener("click",  updateLineNumbers);

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

/* ── Option card selection ───────────────────────────────── */

/* Track which option is currently selected */
let selectedOption = "random"; // "random" | "custom"

function selectOption(option) {

  selectedOption = option;

  if (option === "random") {
    optionRandom.classList.add("selected");
    optionCustom.classList.remove("selected");
    customUrlSection.classList.remove("open");
  } else {
    optionCustom.classList.add("selected");
    optionRandom.classList.remove("selected");
    customUrlSection.classList.add("open");
    /* Focus the input after the slide-down animation */
    setTimeout(() => customCode.focus(), 80);
  }
}

optionRandom.addEventListener("click", () => selectOption("random"));
optionCustom.addEventListener("click", () => selectOption("custom"));

/* ── Modal helpers ───────────────────────────────────────── */

function openModal() {

  shareModal.classList.add("show");
  resetModalUI();
}

function closeModal() {

  shareModal.classList.remove("show");
}

function resetModalUI() {

  /* Reset option to random */
  selectOption("random");

  /* Reset custom input */
  customCode.value = "";
  charCounter.textContent = "0/30";
  charCounter.classList.remove("warn", "over");

  urlInputWrap.classList.remove("valid", "invalid");
  validationIcon.textContent = "";
  validationIcon.classList.remove("show", "ok", "err");

  urlHelper.textContent = "Letters, numbers and hyphens only";
  urlHelper.classList.remove("error-msg", "ok-msg");

  setCreateBtnLoading(false);
}

/* ── Custom URL live validation ──────────────────────────── */

const VALID_SLUG = /^[a-zA-Z0-9-]+$/;

function validateCustomInput(value) {

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

  const ok = VALID_SLUG.test(value) && !value.endsWith(" ");

  urlInputWrap.classList.toggle("valid",   ok);
  urlInputWrap.classList.toggle("invalid", !ok);

  validationIcon.textContent = ok ? "✓" : "✗";
  validationIcon.classList.toggle("ok",  ok);
  validationIcon.classList.toggle("err", !ok);
  validationIcon.classList.add("show");

  if (!ok) {
    urlHelper.textContent = "Only letters, numbers and hyphens allowed";
    urlHelper.classList.add("error-msg");
    urlHelper.classList.remove("ok-msg");
  } else {
    urlHelper.textContent = "Looks good!";
    urlHelper.classList.add("ok-msg");
    urlHelper.classList.remove("error-msg");
  }
}

customCode.addEventListener("input", () => {
  validateCustomInput(customCode.value);
});

/* ── Loading state for create button ─────────────────────── */

function setCreateBtnLoading(isLoading) {

  if (isLoading) {
    createShare.disabled = true;
    createShare.innerHTML = `<span class="btn-spinner"></span>creating...`;
  } else {
    createShare.disabled = false;
    createShare.innerHTML = "create link →";
  }
}

/* ── Page mode helpers ──────────────────────────────────────
   All "on shared URL" state lives in enterViewMode().
   All "on /" state lives in enterHomeMode().
   No other code should touch viewBadge, downloadBtn, shareBar,
   or editWarning directly for mode transitions.
─────────────────────────────────────────────────────────── */

function enterViewMode() {
  viewBadge.classList.add("show");
  downloadBtn.classList.add("show");
}

function enterHomeMode() {
  /* URL */
  history.pushState({}, "", "/");

  /* Editor */
  codeArea.value    = "";
  codeArea.readOnly = false;

  /* UI */
  hideShareBar();
  viewBadge.classList.remove("show");
  downloadBtn.classList.remove("show");

  /* Edit warning */
  hideEditWarning();
  editWarningDismissed = false;

  updateLineNumbers();
  codeArea.focus();
}

/* ── Share modal open ───────────────────────────────────── */

shareBtn.addEventListener("click", () => {

  const code = codeArea.value.trim();

  if (!code) {
    showError("Nothing to share — paste some code first.");
    return;
  }

  openModal();
});

/* Close modal — × button */
modalCloseBtn.addEventListener("click", closeModal);

/* Cancel modal */
cancelShare.addEventListener("click", closeModal);

/* Close on backdrop click */
shareModal.addEventListener("click", (e) => {
  if (e.target === shareModal) closeModal();
});

/* Close on Escape key */
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && shareModal.classList.contains("show")) {
    closeModal();
  }
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

  /* Only use custom value if the custom option is selected */
  let custom = selectedOption === "custom" ? customCode.value : "";

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

  setCreateBtnLoading(true);

  try {

    const response = await fetch("/save", {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      setCreateBtnLoading(false);
      showError(data.detail || "Failed to save.");
      return;
    }

    const fullUrl = window.location.origin + data.url;

    history.pushState({}, "", data.url);

    showShareBar(fullUrl);

    enterViewMode();

    closeModal();

    /* Hide edit warning — they've just created a new URL */
    hideEditWarning();
    editWarningDismissed = false;

  } catch (err) {

    setCreateBtnLoading(false);
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
  enterHomeMode();
});

/* ── Download snippet ───────────────────────────────────── */

downloadBtn.addEventListener("click", () => {

  const code = codeArea.value;

  if (!code) return;

  const blob = new Blob([code], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");

  /* Derive filename from the slug in the URL, fallback to 'code' */
  const slug = window.location.pathname.replace(/^\//, "") || "code";

  a.href     = url;
  a.download = `${slug}.txt`;

  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  URL.revokeObjectURL(url);
});

/* ── Unsaved changes warning on refresh / tab close ────────
   Only fires when user is on '/' (fresh editor) with content.
   Uses native beforeunload — browser renders its own dialog.
─────────────────────────────────────────────────────────── */

window.addEventListener("beforeunload", (e) => {

  if (window.location.pathname === "/" && codeArea.value.trim().length > 0) {
    e.preventDefault();
    /* Required for legacy browser support */
    e.returnValue = "";
  }
});

/* ── Decode + decompress ───────────────────────────────── */

async function decodeAndDecompress(encoded) {

  const std    = encoded.replace(/-/g, "+").replace(/_/g, "/");
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

  const total  = chunks.reduce((sum, c) => sum + c.length, 0);
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

    codeArea.value    = code;
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