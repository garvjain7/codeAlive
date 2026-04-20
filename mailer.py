import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

MAIL_EMAIL = os.getenv("MAIL_EMAIL")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

def send_waitlist_email(to_email: str):
    """
    Sends a confirmation email to a user who joined the waitlist.
    Uses Gmail SMTP with App Passwords.
    """
    if not MAIL_EMAIL or not MAIL_PASSWORD:
        print("Mail credentials not found. Skipping email.")
        return False

    # Create the email content
    subject = "You're on the CodeAlive Waitlist! 🚀"
    body = f"""
    Hi there,

    Thank you for joining the CodeAlive waitlist!

    We're excited to have you. We'll notify you as soon as our real-time 
    collaborative coding rooms are ready for early access.

    In the meantime, feel free to use our instant code sharing editor 
    at https://codealive.onrender.com/editor

    Best,
    The CodeAlive Team
    """

    msg = MIMEMultipart()
    msg['From'] = f"CodeAlive <{MAIL_EMAIL}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to Gmail SMTP server
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(MAIL_EMAIL, MAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False
