/**
 * CodeAlive — workspace.js
 * Modular orchestrator for the workspace page.
 */

import * as dom from './workspace-dom.js';
import { toggleTheme } from '../../core/theme.js';
import { translateError } from '../../core/error-service.js';

// ── STATE ──────────────────────────────────────────────────
let currentView = 'created';
let allData = {
  created: [],
  accessed: [],
  files: []
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

    // 2. Fetch Snippets & Files (all parallel)
    const [createdRes, accessedRes, filesRes] = await Promise.all([
      fetch('/api/workspace/created'),
      fetch('/api/workspace/accessed'),
      fetch('/api/workspace/files')
    ]);

    if (createdRes.ok) {
      const data = await createdRes.json();
      allData.created = data.snippets || [];
    }

    if (accessedRes.ok) {
      const data = await accessedRes.json();
      allData.accessed = data.snippets || [];
    }

    if (filesRes.ok) {
      const data = await filesRes.json();
      allData.files = data.files || [];
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
  dom.statFiles.textContent     = stats.total_files || 0;
  dom.statLanguages.textContent = stats.unique_languages || 0;
  dom.statDownloads.textContent = stats.total_downloads || 0;
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

  if (currentView === 'files') {
    const list = allData.files;
    if (!query) { renderFileCards(list); return; }
    const filtered = list.filter(f => {
      const title = (f.title || '').toLowerCase();
      const name  = (f.original_filename || '').toLowerCase();
      const type  = (f.file_type || '').toLowerCase();
      return title.includes(query) || name.includes(query) || type.includes(query);
    });
    renderFileCards(filtered);
    return;
  }

  const currentList = allData[currentView];
  if (!query) { renderSnippetCards(currentList); return; }

  const filtered = currentList.filter(s => {
    const title  = (s.title || '').toLowerCase();
    const codeId = (s.code_id || '').toLowerCase();
    const lang   = (s.language || '').toLowerCase();
    return title.includes(query) || codeId.includes(query) || lang.includes(query);
  });
  renderSnippetCards(filtered);
}

// ── SNIPPET CARD RENDERING ────────────────────────────────────
function renderSnippetCards(snippets) {
  if (snippets.length === 0) {
    const isSearching = dom.workspaceSearch.value.trim().length > 0;
    dom.snippetList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${isSearching ? '🔍' : '📝'}</div>
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
  const nowDate     = new Date();
  
  const totalDuration = expiryDate - createdDate;
  const remaining     = expiryDate - nowDate;
  let percent = (remaining / totalDuration) * 100;
  percent = Math.max(0, Math.min(100, percent));

  const isExpired = remaining <= 0;
  let progressColor = 'var(--green)';
  if (percent < 20) progressColor = 'var(--error)';
  else if (percent < 50) progressColor = '#f59e0b';

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

// ── FILE CARD RENDERING ───────────────────────────────────────
const FILE_ICONS = {
  'application/pdf': '📄',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '📝',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '📊',
  'application/vnd.ms-excel': '📊',
};
function fileIcon(file_type) {
  if (!file_type) return '📁';
  if (FILE_ICONS[file_type]) return FILE_ICONS[file_type];
  if (file_type.startsWith('image/')) return '🖼️';
  if (file_type.startsWith('video/')) return '🎬';
  if (file_type.startsWith('text/') || file_type === 'application/json') return '📃';
  return '📁';
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderFileCards(files) {
  if (files.length === 0) {
    const isSearching = dom.workspaceSearch.value.trim().length > 0;
    dom.snippetList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${isSearching ? '🔍' : '📁'}</div>
        <h3>${isSearching ? 'No matches found' : 'No files yet'}</h3>
        <p>${isSearching ? 'Try adjusting your search query.' : 'Files you share will appear here.'}</p>
        ${!isSearching ? '<a href="/import" class="btn-action-main" style="color: var(--accent); border-color: var(--accent)">Import your first file</a>' : ''}
      </div>
    `;
    return;
  }
  dom.snippetList.innerHTML = files.map(f => createFileCardHTML(f)).join('');
}

function createFileCardHTML(file) {
  const { file_id, title, original_filename, file_type, file_size_bytes, is_password_protected, expires_at, created_at, download_count } = file;

  const createdDate = new Date(created_at);
  const expiryDate  = new Date(expires_at);
  const nowDate     = new Date();
  const totalDuration = expiryDate - createdDate;
  const remaining     = expiryDate - nowDate;
  let percent = (remaining / totalDuration) * 100;
  percent = Math.max(0, Math.min(100, percent));
  const isExpired = remaining <= 0;
  let progressColor = 'var(--green)';
  if (percent < 20) progressColor = 'var(--error)';
  else if (percent < 50) progressColor = '#f59e0b';
  const daysLeft = Math.ceil(remaining / (1000 * 60 * 60 * 24));
  const expiryText = isExpired ? 'Expired' : `${daysLeft} days remaining`;
  const visibilityLabel = is_password_protected ? 'Protected' : 'Public';
  const icon = fileIcon(file_type);
  const sizeLabel = formatBytes(file_size_bytes);

  return `
    <div class="snippet-card" data-file-id="${file_id}">
      <div class="card-top">
        <div class="card-info">
          <h3 class="snippet-title">${icon} ${title || original_filename || 'Untitled File'}</h3>
          <a href="/f/${file_id}" class="snippet-slug">codealive.onrender.com/f/${file_id} ↗</a>
          <div class="card-badges">
            <span class="badge badge-lang">${sizeLabel}</span>
            <span class="badge badge-lang" style="opacity:0.7">📥 ${download_count || 0}</span>
            <span class="badge ${is_password_protected ? 'badge-protected' : 'badge-visibility'}">${visibilityLabel}</span>
          </div>
        </div>
        <div style="position: relative;">
          <button class="btn-more" data-file-id="${file_id}">⋮</button>
          <div class="action-menu" id="filemenu-${file_id}">
            <a class="menu-item" href="/api/files/${file_id}" download="${original_filename}">📥 Download File</a>
            <button class="menu-item" data-action="file-password" data-file-id="${file_id}">
              ${is_password_protected ? '🔑 Reset Password' : '🔒 Add Password'}
            </button>
            <button class="menu-item" data-action="file-expiry" data-file-id="${file_id}">⏳ Extend Expiry</button>
            <div class="dropdown-divider"></div>
            <button class="menu-item danger" data-action="file-delete" data-file-id="${file_id}">🗑️ Delete File</button>
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
        <a href="/f/${file_id}" class="btn-action-main">Open File</a>
        <button class="btn-action-main btn-copy-link" data-url="${window.location.origin}/f/${file_id}">Copy Link</button>
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
      dom.sidebar.classList.remove('open');
    });
  });

  dom.mobileSidebarToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    dom.sidebar.classList.toggle('open');
  });

  dom.snippetList.addEventListener('click', async (e) => {
    // ── Copy Link (shared by snippets & files)
    if (e.target.classList.contains('btn-copy-link')) {
      const url = e.target.dataset.url;
      navigator.clipboard.writeText(url).then(() => showToast('Link copied to clipboard!'));
      return;
    }

    // ── Snippet "⋮" menu toggle
    if (e.target.classList.contains('btn-more') && e.target.dataset.codeId) {
      e.stopPropagation();
      const codeId = e.target.dataset.codeId;
      const menu = document.getElementById(`menu-${codeId}`);
      document.querySelectorAll('.action-menu.show').forEach(m => { if (m !== menu) m.classList.remove('show'); });
      menu.classList.toggle('show');
      return;
    }

    // ── File "⋮" menu toggle
    if (e.target.classList.contains('btn-more') && e.target.dataset.fileId) {
      e.stopPropagation();
      const fileId = e.target.dataset.fileId;
      const menu = document.getElementById(`filemenu-${fileId}`);
      document.querySelectorAll('.action-menu.show').forEach(m => { if (m !== menu) m.classList.remove('show'); });
      menu.classList.toggle('show');
      return;
    }

    // ── Snippet menu actions
    if (e.target.classList.contains('menu-item') && e.target.dataset.codeId) {
      handleSnippetAction(e.target.dataset.action, e.target.dataset.codeId);
      return;
    }

    // ── File menu actions
    if (e.target.classList.contains('menu-item') && e.target.dataset.fileId) {
      handleFileAction(e.target.dataset.action, e.target.dataset.fileId);
    }
  });

  dom.themeToggle.addEventListener('click', () => {
    toggleTheme(showToast);
  });
}

// ── SNIPPET ACTIONS ───────────────────────────────────────────
async function handleSnippetAction(action, codeId) {
  if (action === 'delete') {
    if (!confirm('Are you sure you want to delete this snippet? This cannot be undone.')) return;
    try {
      const res = await fetch(`/api/workspace/snippets/${codeId}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(translateError(err.detail || { status: res.status }, 'Failed to delete snippet'));
        return;
      }
      showToast('Snippet deleted');
      fetchData();
    } catch (err) {
      showToast(translateError(err, 'Failed to delete snippet'));
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
        showToast(translateError(err.detail || { status: res.status }, 'Failed to update password'));
        return;
      }
      showToast('Password updated');
      fetchData();
    } catch (err) {
      showToast(translateError(err, 'Failed to update password'));
    }
  }

  if (action === 'expiry') {
    const days = prompt('Extend expiry by how many days? (Max lifespan is 90 days from creation)', '30');
    if (!days) return;
    const daysInt = parseInt(days);
    if (isNaN(daysInt) || daysInt < 1) { showToast('Please enter a valid number of days.'); return; }
    try {
      const res = await fetch(`/api/workspace/snippets/${codeId}/expiry`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days: daysInt })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.capped ? 'Snippet extended to its maximum 90-day lifespan' : `Expiry extended by ${daysInt} days`);
        fetchData();
      } else {
        showToast(translateError(data.detail || { status: res.status }, 'Failed to update expiry'));
      }
    } catch (err) {
      showToast(translateError(err, 'Failed to update expiry'));
    }
  }
}

// ── FILE ACTIONS ──────────────────────────────────────────────
async function handleFileAction(action, fileId) {
  if (action === 'file-delete') {
    if (!confirm('Are you sure you want to delete this file? This cannot be undone.')) return;
    try {
      const res = await fetch(`/api/workspace/files/${fileId}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(translateError(err.detail || { status: res.status }, 'Failed to delete file'));
        return;
      }
      showToast('File deleted');
      fetchData();
    } catch (err) {
      showToast(translateError(err, 'Failed to delete file'));
    }
  }

  if (action === 'file-password') {
    const pwd = prompt('Enter new password for this file:');
    if (!pwd) return;
    try {
      const res = await fetch(`/api/workspace/files/${fileId}/password`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(translateError(err.detail || { status: res.status }, 'Failed to update password'));
        return;
      }
      showToast('Password updated');
      fetchData();
    } catch (err) {
      showToast(translateError(err, 'Failed to update password'));
    }
  }

  if (action === 'file-expiry') {
    const days = prompt('Extend expiry by how many days? (Max lifespan is 90 days from creation)', '30');
    if (!days) return;
    const daysInt = parseInt(days);
    if (isNaN(daysInt) || daysInt < 1) { showToast('Please enter a valid number of days.'); return; }
    try {
      const res = await fetch(`/api/workspace/files/${fileId}/expiry`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days: daysInt })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.capped ? 'File extended to its maximum 90-day lifespan' : `Expiry extended by ${daysInt} days`);
        fetchData();
      } else {
        showToast(translateError(data.detail || { status: res.status }, 'Failed to update expiry'));
      }
    } catch (err) {
      showToast(translateError(err, 'Failed to update expiry'));
    }
  }
}

function showToast(msg) {
  dom.toastWorkspace.textContent = msg;
  dom.toastWorkspace.classList.add('show');
  setTimeout(() => dom.toastWorkspace.classList.remove('show'), 2500);
}

