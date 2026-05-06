/**
 * CodeAlive — workspace.js
 * Modular orchestrator for the workspace page.
 */

import * as dom from './workspace-dom.js';

// ── STATE ──────────────────────────────────────────────────
let currentView = 'created'; 
let allSnippets = {
  created: [],
  accessed: []
};

// ── INITIALIZATION ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchData();
  setupEventListeners();
});

// ── API FETCHING ──────────────────────────────────────────────
async function fetchData() {
  try {
    // 1. Fetch Stats & Profile
    const [statsRes, meRes] = await Promise.all([
      fetch('/api/workspace/stats'),
      fetch('/auth/me')
    ]);

    if (statsRes.ok) {
      const stats = await statsRes.json();
      updateStatsUI(stats);
    }

    if (meRes.ok) {
      const me = await meRes.json();
      dom.userEmailDisplay.textContent = me.email;
      dom.avatarInitial.textContent = (me.username || 'U').charAt(0).toUpperCase();
    }

    // 2. Fetch Snippets (Parallel)
    const [createdRes, accessedRes] = await Promise.all([
      fetch('/api/workspace/created'),
      fetch('/api/workspace/accessed')
    ]);

    if (createdRes.ok) {
      const data = await createdRes.json();
      allSnippets.created = data.snippets || [];
    }

    if (accessedRes.ok) {
      const data = await accessedRes.json();
      allSnippets.accessed = data.snippets || [];
    }

    // Initial render
    renderView(currentView);

  } catch (error) {
    console.error('Fetch error:', error);
    dom.snippetList.innerHTML = '<div class="list-loading"><p>Failed to load workspace. Please try again.</p></div>';
  }
}

// ── UI UPDATES ───────────────────────────────────────────────
function updateStatsUI(stats) {
  dom.statTotal.textContent     = stats.total_snippets || 0;
  dom.statActive.textContent    = stats.active_snippets || 0;
  dom.statLanguages.textContent = stats.unique_languages || 0;
  dom.statAccessed.textContent  = stats.accessed_count || 0;
}

function renderView(view) {
  currentView = view;
  applySearch(); 
  updateActiveStates(view);
}

function updateActiveStates(view) {
  dom.navItems.forEach(item => {
    item.classList.toggle('active', item.dataset.view === view);
  });
  
  dom.tabButtons.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === view);
  });
}

// ── SEARCH & FILTERING ───────────────────────────────────────
function applySearch() {
  const query = dom.workspaceSearch.value.toLowerCase().trim();
  const currentList = allSnippets[currentView];
  
  if (!query) {
    renderSnippetCards(currentList);
    return;
  }

  const filtered = currentList.filter(s => {
    const title = (s.title || '').toLowerCase();
    const codeId = (s.code_id || '').toLowerCase();
    const lang = (s.language || '').toLowerCase();
    return title.includes(query) || codeId.includes(query) || lang.includes(query);
  });

  renderSnippetCards(filtered);
}

// ── CARD RENDERING ───────────────────────────────────────────
function renderSnippetCards(snippets) {
  if (snippets.length === 0) {
    const isSearching = dom.workspaceSearch.value.trim().length > 0;
    dom.snippetList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${isSearching ? '🔍' : '📁'}</div>
        <h3>${isSearching ? 'No matches found' : 'No snippets yet'}</h3>
        <p>${isSearching ? 'Try adjusting your search query.' : 'Created snippets will appear here.'}</p>
        ${!isSearching ? '<a href="/editor" class="btn-action-main" style="color: var(--accent); border-color: var(--accent)">Create your first snippet</a>' : ''}
      </div>
    `;
    return;
  }

  dom.snippetList.innerHTML = snippets.map(s => createCardHTML(s)).join('');
}

function createCardHTML(snippet) {
  const { title, code_id, language, is_password_protected, expires_at, created_at } = snippet;
  
  const createdDate = new Date(created_at);
  const expiryDate  = new Date(expires_at);
  const nowDate    = new Date();
  
  const totalDuration = expiryDate - createdDate;
  const remaining     = expiryDate - nowDate;
  let percent       = (remaining / totalDuration) * 100;
  percent = Math.max(0, Math.min(100, percent));

  const isExpired = remaining <= 0;
  
  let progressColor = 'var(--green)';
  if (percent < 20) progressColor = 'var(--error)';
  else if (percent < 50) progressColor = 'var(--amber)';

  const daysLeft = Math.ceil(remaining / (1000 * 60 * 60 * 24));
  const expiryText = isExpired ? 'Expired' : `${daysLeft} days remaining`;
  const visibilityLabel = is_password_protected ? 'Protected' : 'Public';

  return `
    <div class="snippet-card">
      <div class="card-top">
        <div class="card-info">
          <h3 class="snippet-title">${title || 'Untitled Snippet'}</h3>
          <a href="/s/${code_id}" class="snippet-slug">codealive.onrender.com/s/${code_id} ↗</a>
          <div class="card-badges">
            <span class="badge badge-lang">${language || 'text'}</span>
            <span class="badge ${is_password_protected ? 'badge-protected' : 'badge-visibility'}">${visibilityLabel}</span>
          </div>
        </div>
        <button class="btn-more" title="More actions">⋮</button>
      </div>

      <div class="expiry-section">
        <div class="expiry-label">
          ${expiryText}
          <span style="opacity: 0.5; float: right;">${Math.round(percent)}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" style="width: ${percent}%; background: ${progressColor};"></div>
        </div>
      </div>

      <div class="card-actions">
        <a href="/s/${code_id}" class="btn-action-main">Open Snippet</a>
        <button class="btn-action-main btn-copy-link" data-url="${window.location.origin}/s/${code_id}">Copy Link</button>
      </div>
    </div>
  `;
}

// ── EVENT LISTENERS ──────────────────────────────────────────
function setupEventListeners() {
  dom.workspaceSearch.addEventListener('input', applySearch);

  dom.profileToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    dom.profileDropdown.classList.toggle('show');
  });

  document.addEventListener('click', () => {
    dom.profileDropdown.classList.remove('show');
  });

  dom.tabButtons.forEach(btn => {
    btn.addEventListener('click', () => renderView(btn.dataset.tab));
  });

  dom.navItems.forEach(item => {
    item.addEventListener('click', () => renderView(item.dataset.view));
  });

  dom.snippetList.addEventListener('click', (e) => {
    if (e.target.classList.contains('btn-copy-link')) {
      const url = e.target.dataset.url;
      navigator.clipboard.writeText(url).then(() => showToast('Link copied to clipboard!'));
    }
    if (e.target.classList.contains('btn-more')) {
      showToast('Action menu coming soon');
    }
  });

  dom.themeToggle.addEventListener('click', () => {
    showToast('Dark theme is default. Theme switching coming soon.');
  });
}

function showToast(msg) {
  dom.toastWorkspace.textContent = msg;
  dom.toastWorkspace.classList.add('show');
  setTimeout(() => dom.toastWorkspace.classList.remove('show'), 2500);
}
