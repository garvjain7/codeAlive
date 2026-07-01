import { binaryUploadBtn } from "./dom.js";
import { showError, showToast } from "./ui.js";

function createUploadModal() {
  const existing = document.getElementById("binary-upload-modal");
  if (existing) return existing;

  const wrapper = document.createElement("div");
  wrapper.id = "binary-upload-modal";
  wrapper.style.position = "fixed";
  wrapper.style.inset = "0";
  wrapper.style.background = "rgba(0,0,0,0.65)";
  wrapper.style.display = "none";
  wrapper.style.alignItems = "center";
  wrapper.style.justifyContent = "center";
  wrapper.style.zIndex = "2000";

  wrapper.innerHTML = `
    <div style="width:min(540px,90vw);background:#111827;color:#f9fafb;border-radius:14px;padding:24px;box-shadow:0 20px 45px rgba(0,0,0,0.35);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h3 style="margin:0;font-size:1.1rem;">Upload a file</h3>
        <button id="binary-upload-close" style="background:transparent;border:0;color:#f9fafb;font-size:1.25rem;cursor:pointer;">×</button>
      </div>
      <p style="margin:0 0 16px;line-height:1.5;color:#d1d5db;">Upload a supported text/image/document/video file. ZIP files are not supported.</p>
      <input id="binary-upload-input" type="file" style="width:100%;margin-bottom:12px;" />
      <div id="binary-upload-title-row" style="margin-bottom:12px;display:none;">
        <label for="binary-upload-title" style="display:block;margin-bottom:6px;">Title</label>
        <input id="binary-upload-title" type="text" style="width:100%;padding:8px;border-radius:8px;border:1px solid #374151;background:#030712;color:#f9fafb;" placeholder="Give your file a title" />
      </div>
      <div style="display:flex;justify-content:flex-end;gap:8px;">
        <button id="binary-upload-cancel" style="padding:8px 12px;border-radius:8px;border:1px solid #374151;background:transparent;color:#f9fafb;cursor:pointer;">Cancel</button>
        <button id="binary-upload-submit" style="padding:8px 12px;border-radius:8px;border:1px solid #38bdf8;background:#38bdf8;color:#0f172a;font-weight:600;cursor:pointer;">Upload</button>
      </div>
    </div>
  `;

  document.body.appendChild(wrapper);
  return wrapper;
}

export function initBinaryUpload() {
  if (!binaryUploadBtn) return;

  const modal = createUploadModal();
  const closeBtn = document.getElementById("binary-upload-close");
  const cancelBtn = document.getElementById("binary-upload-cancel");
  const submitBtn = document.getElementById("binary-upload-submit");
  const input = document.getElementById("binary-upload-input");
  const titleRow = document.getElementById("binary-upload-title-row");
  const titleInput = document.getElementById("binary-upload-title");

  const openModal = () => {
    modal.style.display = "flex";
  };

  const closeModal = () => {
    modal.style.display = "none";
    input.value = "";
    titleInput.value = "";
    titleRow.style.display = "none";
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
    titleRow.style.display = window.__USER_ID__ ? "block" : "none";
  });

  submitBtn?.addEventListener("click", async () => {
    const [file] = input.files || [];
    if (!file) {
      showError("Please choose a file first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    if (window.__USER_ID__) {
      formData.append("title", titleInput.value.trim());
    }

    try {
      const response = await fetch("/api/files/upload", { method: "POST", body: formData });
      const data = await response.json();
      if (!response.ok) {
        showError(data.detail || "Upload failed.");
        return;
      }
      const fileUrl = `${window.location.origin}/api/files/view/${data.file_id}`;
      showToast(`Upload stored. Open ${fileUrl}`);
      closeModal();
    } catch (error) {
      showError("Network error while uploading file.");
    }
  });
}
