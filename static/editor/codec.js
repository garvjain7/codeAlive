// ── CODEC (CodeMirror 6) ─────────────────────────────────────────────────────────
import { detection } from "./detection.js";
import { highlights, parseHighlights, renderHighlights } from "./highlights.js";
import { setLanguage } from "./editor.js";
import { updateLangBadge, showError, showShareBar } from "../core/ui.js";
import { enterViewMode } from "./modes.js";

// ── DECODE + DECOMPRESS ───────────────────────────────────────────────────────

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

// ── LOAD ENCODED SNIPPET ─────────────────────────────────────────────────────

export async function loadEncodedSnippet(encoded, language = "text", highlightsStr = "") {
  const { view } = await import("../core/dom.js");
  if (!view) return;

  try {
    const code = await decodeAndDecompress(encoded);

    // Set code in editor
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: code },
    });

    detection.status   = "done";
    detection.language = language;

    // Load language extension
    await setLanguage(language);

    // Hydrate highlights
    const parsed = parseHighlights(highlightsStr);
    highlights.length = 0;
    parsed.forEach((h) => highlights.push(h));
    renderHighlights();

    updateLangBadge({ status: detection.status, language: detection.language });
    showShareBar(window.location.href);
    enterViewMode();
    
  } catch (err) {
    showError("Failed to decode snippet.");
    console.error(err);
  }
}
