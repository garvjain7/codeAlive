// ── MODAL ─────────────────────────────────────────────────────────────────────
//
//  • Share modal: open / close / reset
//  • Option card selection (random vs custom)
//  • Custom URL live validation
//  • Create-button state helpers
//  • How-to-highlight modal + triggerHighlightAfterWelcome

import {
  shareModal,
  createShare,
  cancelShare,
  modalCloseBtn,
  customCode,
  charCounter,
  urlInputWrap,
  validationIcon,
  urlHelper,
  customUrlSection,
  optionRandom,
  optionCustom,
  highlightModal,
  highlightCloseBtn,
  highlightGotIt,
  howItWorksBtn,
} from "./dom.js";

import { hideHighlightPopup } from "./highlights.js";

// ── Option card selection ─────────────────────────────────────────────────────

export let selectedOption = "random";

export function selectOption(option) {
  selectedOption = option;
  if (option === "random") {
    optionRandom.classList.add("selected");
    optionCustom.classList.remove("selected");
    customUrlSection.classList.remove("open");
  } else {
    optionCustom.classList.add("selected");
    optionRandom.classList.remove("selected");
    customUrlSection.classList.add("open");
    setTimeout(() => customCode.focus(), 80);
  }
}

optionRandom.addEventListener("click", () => selectOption("random"));
optionCustom.addEventListener("click", () => selectOption("custom"));

// ── Share modal open / close / reset ─────────────────────────────────────────

export function openModal() {
  shareModal.classList.add("show");
  resetModalUI();
}

export function closeModal() {
  shareModal.classList.remove("show");
}

export function resetModalUI() {
  selectOption("random");

  customCode.value = "";
  charCounter.textContent = "0/30";
  charCounter.classList.remove("warn", "over");

  urlInputWrap.classList.remove("valid", "invalid");
  validationIcon.textContent = "";
  validationIcon.classList.remove("show", "ok", "err");

  urlHelper.textContent = "Letters, numbers and hyphens only";
  urlHelper.classList.remove("error-msg", "ok-msg");

  setCreateBtnNormal();
}

modalCloseBtn.addEventListener("click", closeModal);
cancelShare.addEventListener("click", closeModal);

shareModal.addEventListener("click", (e) => {
  if (e.target === shareModal) closeModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (shareModal.classList.contains("show")) closeModal();
    hideHighlightPopup();
  }
});

// ── Custom URL live validation ────────────────────────────────────────────────

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

  urlInputWrap.classList.toggle("valid", ok);
  urlInputWrap.classList.toggle("invalid", !ok);

  validationIcon.textContent = ok ? "✓" : "✗";
  validationIcon.classList.toggle("ok", ok);
  validationIcon.classList.toggle("err", !ok);
  validationIcon.classList.add("show");

  urlHelper.textContent = ok
    ? "Looks good!"
    : "Only letters, numbers and hyphens allowed";
  urlHelper.classList.toggle("ok-msg", ok);
  urlHelper.classList.toggle("error-msg", !ok);
}

customCode.addEventListener("input", () =>
  validateCustomInput(customCode.value),
);

// ── Create-button state helpers ───────────────────────────────────────────────

export function setCreateBtnLoading(msg = "creating...") {
  createShare.disabled = true;
  createShare.innerHTML = `<span class="btn-spinner"></span>${msg}`;
}

export function setCreateBtnNormal() {
  createShare.disabled = false;
  createShare.innerHTML = "create link →";
}

// ── How-to-highlight modal ────────────────────────────────────────────────────

// Open modal
export function openHighlightModal() {
  console.log("Modal element:", highlightModal);
  if (highlightModal) {
    highlightModal.classList.remove("hidden");
  }
}

// Close modal
export function closeHighlightModal() {
  if (highlightModal) {
    highlightModal.classList.add("hidden");
  }
}

// Close actions (X button + Got it)
if (highlightCloseBtn) {
  highlightCloseBtn.addEventListener("click", closeHighlightModal);
}

if (highlightGotIt) {
  highlightGotIt.addEventListener("click", closeHighlightModal);
}

// Open from "How it works" button (ALWAYS works)
if (howItWorksBtn) {
  howItWorksBtn.addEventListener("click", openHighlightModal);
}

// ── triggerHighlightAfterWelcome (called from HTML) ───────────────────────────

// ===============================
// 🚀 Trigger AFTER welcome box hides
// ===============================

// ===============================
// HIGHLIGHT GUIDE MODAL LOGIC
// ===============================

export function triggerHighlightAfterWelcome() {
  // Only show on homepage
  if (window.location.pathname !== "/") return;

  // Don't show again if already seen
  if (localStorage.getItem("seenHighlightGuide") === "true") return;

  setTimeout(() => {
    openHighlightModal();
    localStorage.setItem("seenHighlightGuide", "true");
  }, 600);
}