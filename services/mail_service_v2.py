# =============================================================================
# mail_service_v2.py
# =============================================================================
#
# V1 PROBLEM
# ----------
# mailer.py used smtplib directly from the main Render backend.
# Render free tier blocks outbound SMTP on ports 25, 465, 587.
# Error: [Errno 101] Network is unreachable
#
# V2 SOLUTION
# -----------
# This file calls a separate mail microservice deployed on Fly.io over HTTPS.
# Render allows outbound HTTPS freely.
#
# FLOW
# ----
#   Main backend (Render)
#       ↓  HTTPS POST  +  x-api-key header
#   Mail microservice (Fly.io — SMTP ports open)
#       ↓  smtplib → Gmail port 465
#   User inbox
#
# ENV VARS (set on Render)
# ------------------------
#   MAIL_SERVICE_URL      https://codealive-mail.vercel.app/
#   MAIL_SERVICE_API_KEY  shared secret key
# =============================================================================

import os
import requests
from dotenv import load_dotenv

load_dotenv()

MAIL_SERVICE_URL     = os.getenv("MAIL_SERVICE_URL")
MAIL_SERVICE_API_KEY = os.getenv("MAIL_SERVICE_API_KEY")

# V1 — DEPRECATED (direct SMTP, broken on Render free tier)
# MAIL_EMAIL    = os.getenv("MAIL_EMAIL")
# MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")


def _call_mail_service(endpoint: str, payload: dict) -> bool:
    """
    Internal. Single exit point for all mail calls.
    Attaches the secret key in the header so Fly.io accepts the request.
    Returns True if accepted, False on any failure — always non-fatal.
    """
    if not MAIL_SERVICE_URL or not MAIL_SERVICE_API_KEY:
        print("[mail_service_v2] MAIL_SERVICE_URL or MAIL_SERVICE_API_KEY not set. Skipping.")
        return False

    url = f"{MAIL_SERVICE_URL.rstrip('/')}{endpoint}"
    headers = {
        "x-api-key":    MAIL_SERVICE_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=8)
        response.raise_for_status()
        return True

    except requests.exceptions.Timeout:
        print(f"[mail_service_v2] Timeout reaching {url}. Email not sent.")
        return False

    except requests.exceptions.ConnectionError:
        print(f"[mail_service_v2] Cannot connect to {url}. Email not sent.")
        return False

    except requests.exceptions.HTTPError as e:
        print(f"[mail_service_v2] Mail service error {e.response.status_code}: {e.response.text}")
        return False

    except Exception as e:
        print(f"[mail_service_v2] Unexpected error: {e}")
        return False


def send_waitlist_email(to_email: str) -> bool:
    """Send waitlist confirmation email via the mail microservice."""
    return _call_mail_service("/send/waitlist", {"to": to_email})


def send_reset_email(to_email: str, token: str) -> bool:
    """Send password reset link via the mail microservice."""
    return _call_mail_service("/send/reset-password", {"to": to_email, "token": token})


def send_verification_email(to_email: str, token: str) -> bool:
    """Send account verification email via the mail microservice."""
    return _call_mail_service("/send/verify", {"to": to_email, "token": token})