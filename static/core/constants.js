// ── CONSTANTS ─────────────────────────────────────────────────────────────────

export const MAX_LINES   = 1000;
export const DEBOUNCE_MS = 1000; // ms of inactivity before detection fires on typing
export const COOLDOWN_MS = 2000; // minimum ms between successive detection API calls
export const MIN_LINES   = 8;   // threshold: need at least this many lines …
export const MIN_CHARS   = 100; // … OR this many characters to trigger detection

/* Must match #codeArea / #code-highlight CSS exactly */
export const LINE_HEIGHT = 22; // px — line-height in editor
export const PADDING_TOP = 18; // px — padding-top in editor

// Highlight colors taken from existing Prism palette so the bands feel native.
export const COLOR_POOL = [
  { bg: "rgba(63,  224, 160, 0.10)", border: "#3fe0a0" }, // accent green
  { bg: "rgba(123, 159, 255, 0.10)", border: "#7b9fff" }, // keyword blue
  { bg: "rgba(245, 169, 127, 0.10)", border: "#f5a97f" }, // number orange
  { bg: "rgba(232, 201, 110, 0.10)", border: "#e8c96e" }, // class yellow
  { bg: "rgba(240, 128, 128, 0.10)", border: "#f08080" }, // error red
];