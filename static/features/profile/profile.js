/* ═══════════════════════════════════════════════════════════════
   CodeAlive — profile.js
   Modular logic for the user profile dashboard.
═══════════════════════════════════════════════════════════════ */

import * as dom from './profile-dom.js';
import '../../core/theme.js';
import { translateError } from '../../core/error-service.js';

// ── INITIALIZATION ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchProfileData();
});

// ── DATA FETCHING ──────────────────────────────────────────────
async function fetchProfileData() {
  try {
    const res = await fetch('/api/profile/summary');
    if (!res.ok) throw { status: res.status, message: 'Failed to load profile' };

    const data = await res.json();
    updateUI(data);
  } catch (err) {
    console.error(err);
    showToast(translateError(err, 'Error loading profile data'));
  }
}

// ── UI UPDATES ───────────────────────────────────────────────
function updateUI(data) {
  const { user, stats, languages, recent } = data;

  // 1. Identity Panel
  dom.avatarLarge.textContent = (user.username || 'U').charAt(0).toUpperCase();
  dom.usernameDisplay.textContent = user.username;
  dom.emailMasked.textContent = maskEmail(user.email);
  
  const date = new Date(user.joined_at);
  dom.joinedDate.textContent = `Joined ${date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}`;

  // 2. Stats
  dom.statSnippets.textContent = stats.total;
  dom.statProtected.textContent = stats.protected;
  dom.statLanguages.textContent = stats.languages;

  // 3. Language Distribution
  renderLangChart(languages);

  // 4. Recent Snippets
  renderRecentSnippets(recent);
}

function maskEmail(email) {
  if (!email) return '';
  const [user, domain] = email.split('@');
  return `${user.charAt(0)}***@${domain}`;
}

function renderLangChart(langs) {
  if (!langs || langs.length === 0) {
    dom.langChart.innerHTML = '<p style="color: var(--text3); font-size: 12px; text-align: center;">No snippets created yet.</p>';
    return;
  }

  // Use the top 5 languages
  const topLangs = langs.slice(0, 5);
  
  dom.langChart.innerHTML = `
    <div class="chart-bars">
      ${topLangs.map(l => `
        <div class="chart-row">
          <span class="lang-name">${l.language}</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${l.percentage}%;"></div>
          </div>
          <span class="lang-pc">${l.percentage}%</span>
        </div>
      `).join('')}
    </div>
  `;
}

function renderRecentSnippets(snippets) {
  if (!snippets || snippets.length === 0) {
    dom.recentList.innerHTML = '<p style="color: var(--text3); font-size: 12px; padding: 20px; text-align: center;">No recent snippets.</p>';
    return;
  }

  dom.recentList.innerHTML = snippets.map(s => `
    <a href="/s/${s.code_id}" class="snippet-item">
      <div class="item-main">
        <span class="item-title">${s.title || 'Untitled Snippet'}</span>
        <div class="item-meta">
          <span>${s.language || 'text'}</span>
          <span>•</span>
          <span>${s.is_password_protected ? '🔒 Protected' : '🌐 Public'}</span>
        </div>
      </div>
      <span class="item-arrow">→</span>
    </a>
  `).join('');
}

function showToast(msg) {
  dom.toastProfile.textContent = msg;
  dom.toastProfile.classList.add('show');
  setTimeout(() => dom.toastProfile.classList.remove('show'), 3000);
}

