document.addEventListener('DOMContentLoaded', () => {
  const copyBtn = document.getElementById('copy-share-link');
  const shareInput = document.getElementById('share-link-value');
  const shareModalBtn = document.getElementById('file-view-share-btn');
  const shareModal = document.getElementById('file-view-share-modal');
  const shareModalClose = document.getElementById('file-view-share-close');
  const shareModalLink = document.getElementById('file-view-share-link');
  const copyModalBtn = document.getElementById('file-view-copy-share');

  if (copyBtn && shareInput) {
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(shareInput.value);
        copyBtn.textContent = 'Copied';
        setTimeout(() => {
          copyBtn.textContent = 'Copy link';
        }, 1800);
      } catch (error) {
        copyBtn.textContent = 'Copy failed';
      }
    });
  }

  if (shareModalBtn && shareModal) {
    const openModal = () => {
      if (shareModalLink) {
        shareModalLink.value = shareModalLink.value || window.location.href;
      }
      shareModal.hidden = false;
    };

    const closeModal = () => {
      shareModal.hidden = true;
    };

    shareModalBtn.addEventListener('click', openModal);
    shareModalClose?.addEventListener('click', closeModal);
    shareModal.addEventListener('click', (event) => {
      if (event.target === shareModal) closeModal();
    });

    copyModalBtn?.addEventListener('click', async () => {
      const link = shareModalLink?.value || window.location.href;
      try {
        await navigator.clipboard.writeText(link);
        copyModalBtn.textContent = 'Copied';
        setTimeout(() => {
          copyModalBtn.textContent = 'Copy';
        }, 1800);
      } catch (error) {
        copyModalBtn.textContent = 'Copy failed';
      }
    });
  }
});
