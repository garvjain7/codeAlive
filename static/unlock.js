// ── SNIPPET UNLOCK LOGIC ───────────────────────────────────────────────────────

import { loadEncodedSnippet } from "./codec.js";
import { showError } from "./ui.js";

export function initUnlock() {
  const overlay = document.getElementById("password-overlay");
  if (!overlay) return;

  const unlockBtn = document.getElementById("unlockBtn");
  const unlockPassword = document.getElementById("unlockPassword");
  const unlockError = document.getElementById("unlockError");
  const codeId = window.__CODE_ID__;

  unlockBtn.addEventListener("click", async () => {
    const password = unlockPassword.value;
    if (!password) {
      unlockError.textContent = "Please enter a password.";
      return;
    }

    unlockBtn.disabled = true;
    unlockBtn.textContent = "Unlocking...";
    unlockError.textContent = "";

    try {
      // 1. Verify password via API
      const response = await fetch(`/api/snippets/${codeId}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password })
      });

      const data = await response.json();

      if (!response.ok) {
        unlockError.textContent = data.detail || "Invalid password.";
        unlockBtn.disabled = false;
        unlockBtn.textContent = "Unlock Snippet";
        return;
      }

      // 2. Success! Load snippet and hide overlay
      // The snippet content is now returned directly in the verify response
      const { encoded_content, language, highlights } = data.snippet;
      await loadEncodedSnippet(encoded_content, language, highlights);
      
      overlay.style.opacity = "0";
      setTimeout(() => overlay.remove(), 300);

    } catch (err) {
      console.error(err);
      unlockError.textContent = "Network error. Try again.";
      unlockBtn.disabled = false;
      unlockBtn.textContent = "Unlock Snippet";
    }
  });

  unlockPassword.addEventListener("keypress", (e) => {
    if (e.key === "Enter") unlockBtn.click();
  });
}
