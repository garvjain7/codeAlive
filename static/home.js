/* ═══════════════════════════════════════════════════════════════
   CodeAlive — home.js
   Handles: navbar scroll state, scroll-reveal, typed demo effect
═══════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // ── Navbar: add .scrolled class when page scrolled ─────────────
  const navbar = document.getElementById('navbar');
  window.addEventListener('scroll', () => {
    navbar.classList.toggle('scrolled', window.scrollY > 40);
  }, { passive: true });

  // ── Scroll reveal ───────────────────────────────────────────────
  // Add .reveal to elements that should animate in on scroll
  const revealSelectors = [
    '.step-card', '.feat-card', '.uc-card',
    '.section-title', '.section-label',
    '.collab-left', '.collab-right',
    '.steps-cta', '.cta-title', '.cta-sub', '.cta-actions',
  ];

  revealSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.classList.add('reveal');
    });
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

  // Stagger step cards and feature cards
  document.querySelectorAll('.step-card').forEach((el, i) => {
    el.style.transitionDelay = `${i * 0.08}s`;
  });
  document.querySelectorAll('.feat-card').forEach((el, i) => {
    el.style.transitionDelay = `${i * 0.06}s`;
  });
  document.querySelectorAll('.uc-card').forEach((el, i) => {
    el.style.transitionDelay = `${i * 0.07}s`;
  });

  // ── Typing animation for the editor cursor line ─────────────────
  // The last code line in the hero editor types out after load
  const typingLine = document.querySelector('.hl-line');
  if (typingLine) {
    const originalText = typingLine.innerHTML;
    // Already pre-rendered — just let the cursor blink naturally.
    // If you want a real typed effect, uncomment below:
    /*
    typingLine.innerHTML = '<span class="cursor"></span>';
    const target = 'fetchUser(42).then(console.log);';
    let i = 0;
    const type = () => {
      if (i < target.length) {
        typingLine.innerHTML =
          `<span class="fn">${target.substring(0, i + 1)}</span><span class="cursor"></span>`;
        i++;
        setTimeout(type, 55 + Math.random() * 40);
      }
    };
    setTimeout(type, 1200);
    */
  }

  // ── Sharebar copy button (decorative in mockup) ─────────────────
  const copyBtn = document.querySelector('.sharebar-copy');
  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const original = copyBtn.textContent;
      copyBtn.textContent = 'copied!';
      copyBtn.style.color = 'var(--green)';
      setTimeout(() => {
        copyBtn.textContent = original;
        copyBtn.style.color = '';
      }, 1800);
    });
  }

  // ── Smooth nav link clicks (in-page anchors) ────────────────────
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', e => {
      const target = document.querySelector(link.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  // ── Theme switching ─────────────────────────────────────────────
  const themeToggle = document.getElementById('themeToggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', async () => {
      const { toggleTheme } = await import('./theme.js');
      toggleTheme();
    });
  }

})();