/* ═══════════════════════════════════════════════════════════════
   CodeAlive — waitlist.js
   Handles: form submission, validation, loading/success states
   ═══════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  const form = document.getElementById('waitlist-form');
  const emailInput = document.getElementById('email');
  const submitBtn = document.getElementById('submit-btn');
  const btnText = submitBtn.querySelector('.btn-text');
  const loader = submitBtn.querySelector('.loader');
  const successState = document.getElementById('success-state');
  const errorMessage = document.getElementById('error-message');

  if (!form) return;

  const validateEmail = (email) => {
    return String(email)
      .toLowerCase()
      .match(
        /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/
      );
  };

  const setSubmitting = (isSubmitting) => {
    if (isSubmitting) {
      submitBtn.disabled = true;
      btnText.textContent = 'Joining...';
      loader.classList.remove('hidden');
      errorMessage.classList.add('hidden');
    } else {
      submitBtn.disabled = false;
      btnText.textContent = 'Join Waitlist';
      loader.classList.add('hidden');
    }
  };

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const email = emailInput.value.trim();

    // 1. Client-side validation
    if (!validateEmail(email)) {
      errorMessage.textContent = 'Please enter a valid email address.';
      errorMessage.classList.remove('hidden');
      return;
    }

    setSubmitting(true);

    try {
      // 2. Prepare Form Data
      const formData = new FormData();
      formData.append('email', email);

      // 3. POST to /waitlist
      const response = await fetch('/waitlist', {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        if (data.ok) {
          // 4. Handle Success
          form.classList.add('hidden');
          
          // Update success message if needed
          if (data.message) {
            const successDesc = successState.querySelector('p');
            if (successDesc) successDesc.textContent = "We’ve sent you a confirmation email and will notify you as soon as collaborative rooms go live.";
          }
          
          successState.classList.remove('hidden');
        } else {
          throw new Error('Server returned non-ok status');
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Server error' }));
        // Specifically handle the "Email is already added" case or other detail messages
        throw new Error(errorData.detail || 'Failed to join waitlist');
      }
    } catch (err) {
      console.error('Waitlist submission error:', err);
      errorMessage.textContent = err.message || 'Something went wrong. Please try again later.';
      errorMessage.classList.remove('hidden');
    } finally {
      setSubmitting(false);
    }
  });

  // Clear error on input
  emailInput.addEventListener('input', () => {
    errorMessage.classList.add('hidden');
  });

})();
