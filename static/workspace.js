/**
 * CodeAlive — workspace.js
 * Modular orchestrator for the workspace page.
 */

import * as dom from './workspace-dom.js';
import { toggleTheme } from './theme.js';

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
  else if (percent < 50) progressColor = '#f59e0b'; // Amber

  const daysLeft = Math.ceil(remaining / (1000 * 60 * 60 * 24));
  const expiryText = isExpired ? 'Expired' : `${daysLeft} days remaining`;
  const visibilityLabel = is_password_protected ? 'Protected' : 'Public';

  return `
    <div class="snippet-card" data-code-id="${code_id}">
      <div class="card-top">
        <div class="card-info">
          <h3 class="snippet-title">${title || 'Untitled Snippet'}</h3>
          <a href="/s/${code_id}" class="snippet-slug">codealive.onrender.com/s/${code_id} ↗</a>
          <div class="card-badges">
            <span class="badge badge-lang">${language || 'text'}</span>
            <span class="badge ${is_password_protected ? 'badge-protected' : 'badge-visibility'}">${visibilityLabel}</span>
          </div>
        </div>
        <div style="position: relative;">
          <button class="btn-more" data-code-id="${code_id}">⋮</button>
          <div class="action-menu" id="menu-${code_id}">
            <button class="menu-item" data-action="password" data-code-id="${code_id}">
              ${is_password_protected ? '🔑 Reset Password' : '🔒 Add Password'}
            </button>
            <button class="menu-item" data-action="expiry" data-code-id="${code_id}">⏳ Extend Expiry</button>
            <div class="dropdown-divider"></div>
            <button class="menu-item danger" data-action="delete" data-code-id="${code_id}">🗑️ Delete Snippet</button>
          </div>
        </div>
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
    document.querySelectorAll('.action-menu.show').forEach(m => m.classList.remove('show'));
  });

  dom.tabButtons.forEach(btn => {
    btn.addEventListener('click', () => renderView(btn.dataset.tab));
  });

  dom.navItems.forEach(item => {
    item.addEventListener('click', () => {
      renderView(item.dataset.view);
      dom.sidebar.classList.remove('open'); // Close on mobile after selection
    });
  });

  dom.mobileSidebarToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    dom.sidebar.classList.toggle('open');
  });

  dom.snippetList.addEventListener('click', async (e) => {
    const codeId = e.target.dataset.codeId;

    // 1. Copy Link
    if (e.target.classList.contains('btn-copy-link')) {
      const url = e.target.dataset.url;
      navigator.clipboard.writeText(url).then(() => showToast('Link copied to clipboard!'));
      return;
    }

    // 2. Toggle Menu
    if (e.target.classList.contains('btn-more')) {
      e.stopPropagation();
      const menu = document.getElementById(`menu-${codeId}`);
      document.querySelectorAll('.action-menu.show').forEach(m => {
        if (m !== menu) m.classList.remove('show');
      });
      menu.classList.toggle('show');
      return;
    }

    // 3. Menu Actions
    if (e.target.classList.contains('menu-item')) {
      const action = e.target.dataset.action;
      handleMenuAction(action, codeId);
    }
  });

  dom.themeToggle.addEventListener('click', () => {
    toggleTheme(showToast);
  });
}

async function handleMenuAction(action, codeId) {
  if (action === 'delete') {
    if (!confirm('Are you sure you want to delete this snippet? This cannot be undone.')) return;
    try {
      const res = await fetch(`/api/workspace/snippets/${codeId}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Failed to delete snippet');
        return;
      }
      showToast('Snippet deleted');
      fetchData(); // Refresh list
    } catch (err) {
      showToast('Failed to delete snippet');
    }
  }

  if (action === 'password') {
    const pwd = prompt('Enter new password for this snippet:');
    if (!pwd) return;
    try {
      const res = await fetch(`/api/workspace/snippets/${codeId}/password`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Failed to update password');
        return;
      }
      showToast('Password updated');
      fetchData();
    } catch (err) {
      showToast('Failed to update password');
    }
  }

  if (action === 'expiry') {
    const days = prompt('Extend expiry by how many days? (Max lifespan is 90 days from creation)', '30');
    if (!days) return;
    const daysInt = parseInt(days);
    if (isNaN(daysInt) || daysInt < 1) {
      showToast('Please enter a valid number of days.');
      return;
    }
    try {
      const res = await fetch(`/api/workspace/snippets/${codeId}/expiry`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days: daysInt })
      });
      const data = await res.json();
      if (res.ok) {
        if (data.capped) {
          showToast('Snippet extended to its maximum 90-day lifespan');
        } else {
          showToast(`Expiry extended by ${daysInt} days`);
        }
        fetchData();
      } else {
        showToast(data.detail || 'Failed to update expiry');
      }
    } catch (err) {
      showToast('Failed to update expiry');
    }
  }
}

function showToast(msg) {
  dom.toastWorkspace.textContent = msg;
  dom.toastWorkspace.classList.add('show');
  setTimeout(() => dom.toastWorkspace.classList.remove('show'), 2500);
}
