// ── CODEC ─────────────────────────────────────────────────────────────────────
//
//  • decodeAndDecompress  — URL-safe base64 → gzip decompress → string
//  • loadEncodedSnippet   — decode + hydrate editor state

import { codeArea } from "./dom.js";
import { detection } from "./detection.js";
import { highlights, parseHighlights, renderHighlights } from "./highlights.js";
import { updateLineNumbers, mirrorToHighlight } from "./editor.js";
import { updateLangBadge, showError } from "./ui.js";
import { showShareBar } from "./ui.js";
import { enterViewMode } from "./modes.js";

// ── 22. DECODE + DECOMPRESS ───────────────────────────────────────────────────

export async function decodeAndDecompress(encoded) {
  const std    = encoded.replace(/-/g, "+").replace(/_/g, "/");
  const padded = std + "=".repeat((4 - (std.length % 4)) % 4);
  const binary = atob(padded);

  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

  const ds     = new DecompressionStream("gzip");
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
  let offset   = 0;

  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }

  return new TextDecoder().decode(result);
}

// ── 23. LOAD ENCODED SNIPPET ─────────────────────────────────────────────────

export async function loadEncodedSnippet(encoded, language = "text", highlightsStr = "") {
  try {
    const code = await decodeAndDecompress(encoded);

    codeArea.value    = code;
    codeArea.readOnly = false;

    detection.status   = "done";
    detection.language = language;

    // Mutate highlights array in-place so all modules stay in sync
    const parsed = parseHighlights(highlightsStr);
    highlights.length = 0;
    parsed.forEach((h) => highlights.push(h));
    renderHighlights();

    updateLineNumbers();
    mirrorToHighlight(codeArea.value, detection.language);
    updateLangBadge(detection.status, detection.language);

    showShareBar(window.location.href);
    enterViewMode();
  } catch (err) {
    showError("Failed to decode snippet.");
    console.error(err);
  }
}