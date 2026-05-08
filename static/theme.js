/**
 * CodeAlive — theme.js
 * Shared theme management logic.
 */

export function initTheme() {
    // Always default to dark on load, as per user requirement (no persistence)
    document.documentElement.setAttribute("data-theme", "dark");
}

export function toggleTheme(toastCallback) {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    // Removed localStorage.setItem to avoid persistence
    if (toastCallback) {
        toastCallback(`Theme switched to ${next} mode`);
    }
}

// Initialize on load
initTheme();
