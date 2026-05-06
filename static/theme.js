/**
 * CodeAlive — theme.js
 * Shared theme management logic.
 */

export function initTheme() {
    const saved = localStorage.getItem("theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
}

export function toggleTheme(toastCallback) {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    if (toastCallback) {
        toastCallback(`Theme switched to ${next} mode`);
    }
}

// Initialize on load
initTheme();
