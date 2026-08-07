// ── DOM REFERENCES ────────────────────────────────────────────────────────────

// ── DOM REFERENCES ────────────────────────────────────────────────────────────
export const editorContainer = document.getElementById("editor-container");
export let view = null; // To be populated by editor.js
export function setView(v) { view = v; }
export function getView() { return view; }

export const lineInfo     = document.getElementById("lineInfo");
export const charInfo     = document.getElementById("charInfo");

/* Floating popup for highlight selection */
export const highlightPopup    = document.getElementById("highlight-popup");
export const popupHighlightBtn = document.getElementById("popupHighlightBtn");
export const popupRemoveBtn    = document.getElementById("popupRemoveBtn");

/* Language indicator in topbar */
export const langDot   = document.getElementById("langDot");
export const langBadge = document.getElementById("langBadge");

export const copyCodeBtn = document.getElementById("copyCodeBtn");
export const searchBtn   = document.getElementById("searchBtn");
export const shareBtn    = document.getElementById("shareBtn");
export const newBtn      = document.getElementById("newBtn");
export const downloadBtn = document.getElementById("downloadBtn");
export const fileImportBtn = document.getElementById("fileImportBtn");
export const binaryUploadBtn = document.getElementById("binaryUploadBtn");

export const shareBar = document.getElementById("share-bar");
export const shareUrl = document.getElementById("shareUrl");
export const copyBtn  = document.getElementById("copyBtn");

export const errorBar  = document.getElementById("error-bar");
export const toast     = document.getElementById("toast");
export const viewBadge = document.getElementById("view-badge");

/* Share modal */
export const shareModal      = document.getElementById("share-modal");
export const createShare     = document.getElementById("createShare");
export const cancelShare     = document.getElementById("cancelShare");
export const modalCloseBtn   = document.getElementById("modalCloseBtn");
export const customCode      = document.getElementById("customCode");
export const charCounter     = document.getElementById("charCounter");
export const urlInputWrap    = document.getElementById("urlInputWrap");
export const validationIcon  = document.getElementById("validationIcon");
export const urlHelper       = document.getElementById("urlHelper");
export const customUrlSection = document.getElementById("customUrlSection");
export const optionRandom    = document.getElementById("optionRandom");
export const optionCustom    = document.getElementById("optionCustom");
export const snippetPassword = document.getElementById("snippetPassword");
export const expiryDays      = document.getElementById("expiryDays");
export const snippetTitle    = document.getElementById("snippetTitle");

export const editWarning        = document.getElementById("edit-warning");
export const ewDismiss          = document.getElementById("ewDismiss");
export const editorHintEmpty    = document.getElementById("editor-hint-empty");
export const editorHintHighlight = document.getElementById("editor-hint-highlight");

/* How to Highlight modal */
export const highlightModal   = document.getElementById("highlightModal");
export const highlightCloseBtn = document.getElementById("highlightCloseBtn");
export const highlightGotIt   = document.getElementById("highlightGotIt");
export const howItWorksBtn    = document.getElementById("howItWorksBtn");