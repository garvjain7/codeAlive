// ── HIGHLIGHTS (CodeMirror 6) ───────────────────────────────────────────────────
import {
  Decoration,
  EditorView,
} from "https://esm.sh/@codemirror/view";
import {
  StateField,
  StateEffect,
} from "https://esm.sh/@codemirror/state";

import {
  highlightPopup,
  popupHighlightBtn,
  popupRemoveBtn,
  editorContainer,
} from "./dom.js";

import { COLOR_POOL } from "./constants.js";

// ── Effects & Fields ──────────────────────────────────────────────────────────

const setHighlightsEffect = StateEffect.define();

export const highlightsField = StateField.define({
  create() {
    return Decoration.none;
  },
  update(highlights, tr) {
    for (let e of tr.effects) {
      if (e.is(setHighlightsEffect)) {
        highlights = e.value;
      }
    }
    return highlights;
  },
  provide: (f) => EditorView.decorations.from(f),
});

// ── State ─────────────────────────────────────────────────────────────────────

// Internal tracking of highlight ranges for serialization
// Array of { id, start, end } where start/end are 1-based line numbers.
export let highlights = [];
let pendingSelection = null; // { startLine, endLine, targetHighlight }
let hlIdCounter = 0;

function nextHlId() {
  return `hl_${Date.now()}_${hlIdCounter++}`;
}

// ── Serialize / parse ─────────────────────────────────────────────────────────

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

export function serializeHighlights(hls) {
  if (!hls.length) return "";
  return [...hls]
    .sort((a, b) => a.start - b.start)
    .map((h) => (h.start === h.end ? `L${h.start}` : `L${h.start}-L${h.end}`))
    .join(",");
}

// ── Render ────────────────────────────────────────────────────────────────────

export async function renderHighlights() {
  const { view } = await import("./dom.js");
  if (!view) return;

  const decorations = [];
  highlights.forEach((h, idx) => {
    const color = COLOR_POOL[idx % COLOR_POOL.length];
    const deco = Decoration.line({
      attributes: { 
        class: "cm-line-highlight",
        style: `background-color: ${color.bg} !important; border-left: 3px solid ${color.border} !important;`
      }
    });

    for (let i = h.start; i <= h.end; i++) {
      try {
        const line = view.state.doc.line(i);
        decorations.push(deco.range(line.from));
      } catch (e) {
        // Line might not exist yet
      }
    }
  });

  view.dispatch({
    effects: setHighlightsEffect.of(Decoration.set(decorations, true)),
  });
}

// ── Popup ─────────────────────────────────────────────────────────────────────

export function hideHighlightPopup() {
  highlightPopup.classList.remove("show");
  pendingSelection = null;
}

export async function showHighlightPopup(startLine, endLine, targetHighlight) {
  const { view } = await import("./dom.js");
  if (!view) return;

  const rect = editorContainer.getBoundingClientRect();
  
  // Get position of the last line in selection
  const line = view.state.doc.line(endLine);
  const coords = view.coordsAtPos(line.from);
  
  if (!coords) return;

  const top = Math.min(coords.bottom + 6, window.innerHeight - 52);
  const left = coords.left + 12;

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

export function addHighlight(startLine, endLine) {
  highlights.push({ id: nextHlId(), start: startLine, end: endLine });
  renderHighlights();
}

export function removeHighlight(id) {
  highlights = highlights.filter((h) => h.id !== id);
  renderHighlights();
}

export function updateHighlight(id, startLine, endLine) {
  const h = highlights.find((x) => x.id === id);
  if (!h) return;
  h.start = startLine;
  h.end = endLine;
  renderHighlights();
}

// ── Selection Handler ─────────────────────────────────────────────────────────

export async function handleTextSelection() {
  if (window.location.pathname !== "/editor") return;

  const { view } = await import("./dom.js");
  if (!view) return;

  const { from, to } = view.state.selection.main;
  if (from === to) {
    hideHighlightPopup();
    return;
  }

  const startLine = view.state.doc.lineAt(from).number;
  const endLine = view.state.doc.lineAt(to).number;

  const overlapping = highlights.filter(
    (h) => !(h.end < startLine || h.start > endLine)
  );

  let target = null;
  if (overlapping.length > 0) {
    overlapping.sort((a, b) => {
      const overlapA = Math.min(a.end, endLine) - Math.max(a.start, startLine);
      const overlapB = Math.min(b.end, endLine) - Math.max(b.start, startLine);
      return overlapB - overlapA;
    });
    target = overlapping[0];
  }

  showHighlightPopup(startLine, endLine, target);
}

// ── Event Wiring (Called from main.js) ────────────────────────────────────────

export function initHighlights() {
  popupHighlightBtn.addEventListener("click", async () => {
    if (!pendingSelection) return;
    if (pendingSelection.targetHighlight) {
      updateHighlight(
        pendingSelection.targetHighlight.id,
        pendingSelection.startLine,
        pendingSelection.endLine
      );
    } else {
      addHighlight(pendingSelection.startLine, pendingSelection.endLine);
    }
    hideHighlightPopup();
    const { view } = await import("./dom.js");
    if (view) view.focus();
  });

  popupRemoveBtn.addEventListener("click", async () => {
    if (!pendingSelection || !pendingSelection.targetHighlight) return;
    removeHighlight(pendingSelection.targetHighlight.id);
    hideHighlightPopup();
    const { view } = await import("./dom.js");
    if (view) view.focus();
  });

  document.addEventListener("mousedown", (e) => {
    if (!highlightPopup.contains(e.target) && !editorContainer.contains(e.target))
      hideHighlightPopup();
  });
}