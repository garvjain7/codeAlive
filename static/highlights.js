// ── HIGHLIGHTS ────────────────────────────────────────────────────────────────
//
//  Owns:
//    • highlights[]  — the canonical list of { id, start, end } objects
//    • pendingSelection — the selection currently shown in the popup
//    • parse / serialize helpers
//    • render (bands) + scroll sync
//    • popup show / hide
//    • CRUD: add / remove / update
//    • text-selection handler wired to codeArea

import {
  codeArea,
  highlightBands,
  highlightPopup,
  popupHighlightBtn,
  popupRemoveBtn,
} from "./dom.js";

import { COLOR_POOL, LINE_HEIGHT, PADDING_TOP } from "./constants.js";

// ── State ─────────────────────────────────────────────────────────────────────

// highlights: Array of { id, start, end } where start/end are 1-based line numbers.
export let highlights = [];
let pendingSelection = null; // { startLine, endLine, targetHighlight }
let hlIdCounter = 0;

// ── ID helper ─────────────────────────────────────────────────────────────────

function nextHlId() {
  return `hl_${Date.now()}_${hlIdCounter++}`;
}

// ── Serialize / parse ─────────────────────────────────────────────────────────

// "L6-L14,L32-L49" → [{id,start,end}, ...]
export function parseHighlights(str) {
  if (!str || !str.trim()) return [];
  return str
    .split(",")
    .map((part) => {
      const m = part.trim().match(/^L(\d+)(?:-L(\d+))?$/i);
      if (!m) return null;
      const start = parseInt(m[1], 10);
      const end = m[2] ? parseInt(m[2], 10) : start;
      if (isNaN(start) || isNaN(end) || start < 1 || end < start) return null;
      return { id: nextHlId(), start, end };
    })
    .filter(Boolean);
}

// [{ start, end }, ...] → "L6-L14,L32-L49"
export function serializeHighlights(hls) {
  if (!hls.length) return "";
  return [...hls]
    .sort((a, b) => a.start - b.start)
    .map((h) => (h.start === h.end ? `L${h.start}` : `L${h.start}-L${h.end}`))
    .join(",");
}

// ── Scroll sync ───────────────────────────────────────────────────────────────

export function syncHighlightBandsScroll() {
  // translate scrollTop so bands line up with code text.
  highlightBands.style.transform = `translateY(-${codeArea.scrollTop}px)`;
}

// ── Render ────────────────────────────────────────────────────────────────────

export function renderHighlights() {
  highlightBands.innerHTML = "";

  highlights.forEach((h, i) => {
    const color = COLOR_POOL[i % COLOR_POOL.length];
    const band = document.createElement("div");
    band.className = "highlight-band";
    band.style.top = `${PADDING_TOP + (h.start - 1) * LINE_HEIGHT}px`;
    band.style.height = `${(h.end - h.start + 1) * LINE_HEIGHT}px`;
    band.style.background = color.bg;
    band.style.borderLeft = `3px solid ${color.border}`;
    highlightBands.appendChild(band);
  });

  syncHighlightBandsScroll();
}

// ── Popup ─────────────────────────────────────────────────────────────────────

export function hideHighlightPopup() {
  highlightPopup.classList.remove("show");
  pendingSelection = null;
}

export function showHighlightPopup(startLine, endLine, targetHighlight) {
  const rect = codeArea.getBoundingClientRect();

  const rawTop =
    rect.top + PADDING_TOP + endLine * LINE_HEIGHT - codeArea.scrollTop + 6;
  const top = Math.min(rawTop, window.innerHeight - 52);

  const lnWidth = parseInt(
    getComputedStyle(document.documentElement).getPropertyValue("--ln-width") ||
      "52",
    10,
  );
  const left = rect.left + lnWidth + 12;

  highlightPopup.style.top = `${top}px`;
  highlightPopup.style.left = `${left}px`;
  pendingSelection = { startLine, endLine, targetHighlight };

  if (targetHighlight) {
    popupHighlightBtn.textContent = "↔ resize highlighted lines";
    popupHighlightBtn.style.display = "inline-flex";
    popupRemoveBtn.style.display = "inline-flex";
  } else {
    popupHighlightBtn.textContent = "⬛ highlight lines";
    popupHighlightBtn.style.display = "inline-flex";
    popupRemoveBtn.style.display = "none";
  }

  highlightPopup.classList.add("show");
}

// ── CRUD ──────────────────────────────────────────────────────────────────────

function onHighlightsChanged() {
  renderHighlights();
}

export function addHighlight(startLine, endLine) {
  highlights.push({ id: nextHlId(), start: startLine, end: endLine });
  onHighlightsChanged();
}

export function removeHighlight(id) {
  highlights = highlights.filter((h) => h.id !== id);
  onHighlightsChanged();
}

export function updateHighlight(id, startLine, endLine) {
  const h = highlights.find((x) => x.id === id);
  if (!h) return;
  h.start = startLine;
  h.end = endLine;
  onHighlightsChanged();
}

// ── Overlap helper ────────────────────────────────────────────────────────────

function overlapLen(h, startLine, endLine) {
  // Inclusive overlap length in lines.
  const a = Math.max(h.start, startLine);
  const b = Math.min(h.end, endLine);
  if (b < a) return 0;
  return b - a + 1;
}

// ── Text-selection handler ────────────────────────────────────────────────────

function handleTextSelection() {
  // Popup only appears on '/editor' (editor mode). On shared URLs this stays hidden.
  if (window.location.pathname !== "/editor") return;

  const { selectionStart, selectionEnd } = codeArea;
  if (selectionStart === selectionEnd) {
    hideHighlightPopup();
    return;
  }

  const textBefore   = codeArea.value.substring(0, selectionStart);
  const textSelected = codeArea.value.substring(selectionStart, selectionEnd);

  const startLine = textBefore.split("\n").length;
  const endLine   = startLine + textSelected.split("\n").length - 1;

  // Find all highlights that overlap this selection.
  // If multiple overlaps exist, edit the one with the largest overlap length.
  const overlappingHighlights = highlights.filter(
    (h) => !(h.end < startLine || h.start > endLine),
  );

  let target = null;
  if (overlappingHighlights.length > 0) {
    // Prefer highlights that contain the selection start line.
    // This makes resizing deterministic when multiple highlights overlap
    // on common lines.
    const containingStart = overlappingHighlights.filter(
      (h) => h.start <= startLine && h.end >= startLine,
    );

    const pool =
      containingStart.length > 0 ? containingStart : overlappingHighlights;
    pool.sort((a, b) => {
      const da = overlapLen(a, startLine, endLine);
      const db = overlapLen(b, startLine, endLine);
      if (db !== da) return db - da; // larger overlap first
      // Tie-break: choose the one with later start (more specific)
      return b.start - a.start;
    });

    target = pool[0];
  }

  showHighlightPopup(startLine, endLine, target);
}

// ── Event wiring ──────────────────────────────────────────────────────────────

// Show popup after mouse selection
codeArea.addEventListener("mouseup", handleTextSelection);
// Show popup after keyboard selection (Shift+Arrow)
codeArea.addEventListener("keyup", (e) => {
  if (e.shiftKey) handleTextSelection();
});

popupHighlightBtn.addEventListener("click", () => {
  if (!pendingSelection) return;
  if (pendingSelection.targetHighlight) {
    updateHighlight(
      pendingSelection.targetHighlight.id,
      pendingSelection.startLine,
      pendingSelection.endLine,
    );
  } else {
    addHighlight(pendingSelection.startLine, pendingSelection.endLine);
  }
  hideHighlightPopup();
  codeArea.focus();
});

popupRemoveBtn.addEventListener("click", () => {
  if (!pendingSelection || !pendingSelection.targetHighlight) return;
  removeHighlight(pendingSelection.targetHighlight.id);
  hideHighlightPopup();
  codeArea.focus();
});

document.addEventListener("mousedown", (e) => {
  if (!highlightPopup.contains(e.target) && e.target !== codeArea)
    hideHighlightPopup();
});

// Hide popup when the user types + clean stale highlights
codeArea.addEventListener("input", () => {
  hideHighlightPopup();
  const totalLines = codeArea.value.split("\n").length;
  highlights = highlights
    .filter((h) => h.start <= totalLines)
    .map((h) => ({ ...h, end: Math.min(h.end, totalLines) }));
  renderHighlights();
});