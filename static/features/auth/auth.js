/* ═══════════════════════════════════════════════════════════════
   CodeAlive — auth.js (ES Module)
   Frontend logic for Login, Signup, and Reset Password.
   Aligned with project architecture (modular).
═══════════════════════════════════════════════════════════════ */

import { showError, showToast } from "../../core/ui.js";

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    const signupForm = document.getElementById('signupForm');
    const resetForm = document.getElementById('resetForm');
    const forgotPasswordForm = document.getElementById('forgotPasswordForm');
    
    // ── LOGIN HANDLER ───────────────────────────────────────────
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const identifier = document.getElementById('identifier').value;
            const password = document.getElementById('password').value;
            
            const attemptLogin = async () => {
                try {
                    const response = await fetch('/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ identifier, password })
                    });
                    
                    const data = await response.json();
                    if (response.ok) {
                        showToast("Login successful! Redirecting...", 1000);
                        const urlParams = new URLSearchParams(window.location.search);
                        const next = urlParams.get('next') || '/';
                        setTimeout(() => {
                            window.location.href = next;
                        }, 1000);
                    } else {
                        showError(data.detail || { status: response.status });
                    }
                } catch (err) {
                    console.error(err);
                    showError(err, { retryFn: attemptLogin });
                }
            };
            await attemptLogin();
        });
    }
    
    // ── SIGNUP HANDLER ──────────────────────────────────────────
    if (signupForm) {
        signupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (password !== confirmPassword) {
                showError('Passwords do not match');
                return;
            }
            
            const attemptSignup = async () => {
                try {
                    const response = await fetch('/auth/signup', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, email, password })
                    });
                    
                    const data = await response.json();
                    if (response.ok) {
                        showToast("Account created! Please log in.", 2000);
                        const urlParams = new URLSearchParams(window.location.search);
                        const next = urlParams.get('next');
                        const loginUrl = next ? `/login?next=${encodeURIComponent(next)}` : '/login';
                        setTimeout(() => {
                            window.location.href = loginUrl;
                        }, 2000);
                    } else {
                        showError(data.detail || { status: response.status });
                    }
                } catch (err) {
                    console.error(err);
                    showError(err, { retryFn: attemptSignup });
                }
            };
            await attemptSignup();
        });
    }

    // ── RESET PASSWORD HANDLER ──────────────────────────────────
    if (resetForm) {
        resetForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const password = document.getElementById('newPassword').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (password !== confirmPassword) {
                showError('Passwords do not match');
                return;
            }

            // Get token from URL
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token');

            if (!token) {
                showError('Reset token is missing from URL');
                return;
            }

            const attemptReset = async () => {
                try {
                    const response = await fetch('/auth/reset-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ token, new_password: password })
                    });

                    const data = await response.json();
                    if (response.ok) {
                        showToast('Password reset successful! Redirecting...', 2000);
                        setTimeout(() => {
                            window.location.href = '/login';
                        }, 2000);
                    } else {
                        showError(data.detail || { status: response.status });
                    }
                } catch (err) {
                    console.error(err);
                    showError(err, { retryFn: attemptReset });
                }
            };
            await attemptReset();
        });
    }

    // ── FORGOT PASSWORD MODAL ───────────────────────────────────
    const openModalBtn = document.getElementById('openForgotPassword');
    const closeModalBtn = document.getElementById('closeModal');
    const modalOverlay = document.getElementById('modalOverlay');

    if (openModalBtn) {
        openModalBtn.addEventListener('click', (e) => {
            e.preventDefault();
            modalOverlay.classList.add('active');
        });
    }

    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', () => {
            modalOverlay.classList.remove('active');
        });
    }

    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) {
                modalOverlay.classList.remove('active');
            }
        });
    }

    if (forgotPasswordForm) {
        forgotPasswordForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('forgotEmail').value;
            
            const btn = forgotPasswordForm.querySelector('button');
            const originalText = btn.textContent;
            btn.textContent = 'Sending...';
            btn.disabled = true;

            try {
                const response = await fetch('/auth/forgot-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });

                // We always show success for security
                showToast('If the email is correct, a reset link has been sent.', 3000);
                modalOverlay.classList.remove('active');
                forgotPasswordForm.reset();
            } catch (err) {
                console.error(err);
                showError('Network error. Please try again.');
            } finally {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        });
    }
});


