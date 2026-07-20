import { binaryUploadBtn } from "./dom.js";
import { showError, showToast } from "./ui.js";

let openUploadModal = null;

function createUploadModal() {
  const existing = document.getElementById("binary-upload-modal");
  if (existing) return existing;

  const wrapper = document.createElement("div");
  wrapper.id = "binary-upload-modal";
  wrapper.style.position = "fixed";
  wrapper.style.inset = "0";
  wrapper.style.background = "rgba(0,0,0,0.7)";
  wrapper.style.display = "none";
  wrapper.style.alignItems = "center";
  wrapper.style.justifyContent = "center";
  wrapper.style.zIndex = "2000";
  wrapper.style.padding = "20px";

  wrapper.innerHTML = `
    <div style="width:min(560px,100%);background:#0f172a;color:#f8fafc;border-radius:18px;padding:24px;box-shadow:0 20px 50px rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.08);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <div>
          <div style="display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:999px;background:rgba(63,224,160,0.12);color:#3fe0a0;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px;">Share file</div>
          <h3 style="margin:0;font-size:1.1rem;">Create a public file share</h3>
        </div>
        <button id="binary-upload-close" style="background:transparent;border:0;color:#f9fafb;font-size:1.25rem;cursor:pointer;">×</button>
      </div>
      <p id="binary-upload-helper" style="margin:0 0 16px;line-height:1.6;color:#cbd5e1;">Upload a supported file and create a share link in the same flow as snippets.</p>
      <input id="binary-upload-input" type="file" style="width:100%;margin-bottom:12px;" />
      <div id="binary-upload-title-row" style="margin-bottom:12px;display:none;">
        <label for="binary-upload-title" style="display:block;margin-bottom:6px;color:#e2e8f0;">Title</label>
        <input id="binary-upload-title" type="text" style="width:100%;padding:10px 12px;border-radius:12px;border:1px solid #334155;background:#020617;color:#f8fafc;" placeholder="Give the file a title" />
      </div>
      <div id="binary-upload-protection-row" style="margin-bottom:12px;display:none;">
        <label for="binary-upload-password" style="display:block;margin-bottom:6px;color:#e2e8f0;">Password (optional)</label>
        <input id="binary-upload-password" type="password" style="width:100%;padding:10px 12px;border-radius:12px;border:1px solid #334155;background:#020617;color:#f8fafc;" placeholder="Protect this file with a password" />
      </div>
      <div id="binary-upload-expiry-row" style="margin-bottom:12px;display:none;">
        <label for="binary-upload-expiry" style="display:block;margin-bottom:6px;color:#e2e8f0;">Expiry</label>
        <select id="binary-upload-expiry" style="width:100%;padding:10px 12px;border-radius:12px;border:1px solid #334155;background:#020617;color:#f8fafc;">
          <option value="1">1 day</option>
          <option value="7">7 days</option>
          <option value="30" selected>30 days</option>
          <option value="90">90 days</option>
        </select>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:8px;">
        <button id="binary-upload-cancel" style="padding:10px 14px;border-radius:10px;border:1px solid #334155;background:transparent;color:#f9fafb;cursor:pointer;">Cancel</button>
        <button id="binary-upload-submit" style="padding:10px 14px;border-radius:10px;border:1px solid #38bdf8;background:#38bdf8;color:#0f172a;font-weight:600;cursor:pointer;">Create link →</button>
      </div>
    </div>
  `;

  document.body.appendChild(wrapper);
  return wrapper;
}

export function openBinaryUploadModal() {
  if (openUploadModal) {
    openUploadModal();
  }
}

export function initBinaryUpload() {
  if (!binaryUploadBtn) return;

  const modal = createUploadModal();
  const closeBtn = document.getElementById("binary-upload-close");
  const cancelBtn = document.getElementById("binary-upload-cancel");
  const submitBtn = document.getElementById("binary-upload-submit");
  const helperText = document.getElementById("binary-upload-helper");
  const input = document.getElementById("binary-upload-input");
  const titleRow = document.getElementById("binary-upload-title-row");
  const titleInput = document.getElementById("binary-upload-title");
  const protectionRow = document.getElementById("binary-upload-protection-row");
  const passwordInput = document.getElementById("binary-upload-password");
  const expiryRow = document.getElementById("binary-upload-expiry-row");
  const expiryInput = document.getElementById("binary-upload-expiry");

  const openModal = () => {
    const isLoggedIn = Boolean(window.__USER_ID__);
    helperText.textContent = isLoggedIn
      ? "Signed-in users can add a title, password, and expiry before creating the share."
      : "Anyone with the link can view this file. Sign in for password protection and expiry controls.";
    modal.style.display = "flex";
  };

  openUploadModal = openModal;

  const closeModal = () => {
    modal.style.display = "none";
    input.value = "";
    titleInput.value = "";
    passwordInput.value = "";
    titleRow.style.display = "none";
    protectionRow.style.display = "none";
    expiryRow.style.display = "none";
  };

  binaryUploadBtn.addEventListener("click", openModal);
  closeBtn?.addEventListener("click", closeModal);
  cancelBtn?.addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  input?.addEventListener("change", () => {
    const [file] = input.files || [];
    if (!file) return;
    const isLoggedIn = Boolean(window.__USER_ID__);
    titleRow.style.display = isLoggedIn ? "block" : "none";
    protectionRow.style.display = isLoggedIn ? "block" : "none";
    expiryRow.style.display = isLoggedIn ? "block" : "none";
  });

  if (window.__AUTO_OPEN_UPLOAD__) {
    setTimeout(() => openModal(), 180);
  }

  submitBtn?.addEventListener("click", async () => {
    const [file] = input.files || [];
    if (!file) {
      showError("Please choose a file first.");
      return;
    }

    if (window.__USER_ID__) {
      const titleValue = titleInput.value.trim();
      if (!titleValue) {
        showError("Please enter a title for the share.");
        return;
      }
    }

    const formData = new FormData();
    formData.append("file", file);
    if (window.__USER_ID__) {
      formData.append("title", titleInput.value.trim());
      formData.append("password", passwordInput.value || "");
      formData.append("expires_in_days", expiryInput.value || "30");
    }

    try {
      const response = await fetch("/api/files/upload", { method: "POST", body: formData });
      const data = await response.json();
      if (!response.ok) {
        showError(data.detail || data.message || "Unable to create the share.");
        return;
      }
      const fileUrl = `${window.location.origin}${data.url || `/f/${data.file_id}`}`;
      showToast("Share link ready.");
      window.open(fileUrl, "_blank", "noopener,noreferrer");
      closeModal();
    } catch (error) {
      showError("Network error while creating the share.");
    }
  });
}
