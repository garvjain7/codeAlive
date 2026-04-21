// ── MOBILE NAVIGATION ────────────────────────────────────────────────────────
//
//  Handles the hamburger menu toggle and overlay states for mobile viewports.
//  Used on: home.html, waitlist.html
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.getElementById("mobile-menu-toggle");
  const overlay   = document.getElementById("mobile-nav-overlay");
  const mLinks    = document.querySelectorAll(".m-link, .m-link-cta");

  if (!toggleBtn || !overlay) return;

  function toggleMenu() {
    const isOpen = overlay.classList.toggle("open");
    toggleBtn.classList.toggle("active");
    
    // Prevent body scroll when menu is open
    document.body.style.overflow = isOpen ? "hidden" : "";
  }

  toggleBtn.addEventListener("click", toggleMenu);

  // Close menu when a link is clicked (important for fragment identifiers)
  mLinks.forEach(link => {
    link.addEventListener("click", () => {
      overlay.classList.remove("open");
      toggleBtn.classList.remove("active");
      document.body.style.overflow = "";
    });
  });
});
