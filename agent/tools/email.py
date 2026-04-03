"""
tools/email.py
──────────────
Responsibility : Send emails via Gmail SMTP.
                 No AI logic. Pure execution.

Dependencies:
    smtplib — built into Python, no install needed

Setup:
    1. Google Account → Security → 2-Step Verification (must be ON)
    2. Security → App Passwords → generate for "Mail"
    3. Add to .env:
         GMAIL_SENDER=your@gmail.com
         GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

Input contract (JSON string):
    send_email → '{"to": "someone@gmail.com", "subject": "Hello", "body": "Message here"}'
"""

import json
import logging
import smtplib
from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


# ── Output helpers ──────────────────────────────────────────────────────────────

def _ok(data: str) -> str:
    return json.dumps({"status": "success", "data": data}, ensure_ascii=False)

def _err(message: str) -> str:
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


# ── Safe input parser ───────────────────────────────────────────────────────────

def _parse_input(raw: str) -> dict:
    """
    Parse JSON input safely.
    Fallback: if raw is not JSON, treat as email body with no subject/to.
    This lets LLM pass plain text without crashing the tool.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("send_email: non-JSON input, treating as body fallback")
        # Fallback — raw string treated as body, caller must provide to/subject
        return {"body": raw.strip()}


# ── Tool function ───────────────────────────────────────────────────────────────

def send_email(input: str) -> str:
    """
    Send an email via Gmail SMTP.

    Input JSON:
        {
            "to":      "recipient@example.com",  ← required
            "subject": "Subject line",            ← required
            "body":    "Email body text"          ← required
        }

    Optional:
        "cc":  "cc@example.com"
        "bcc": "bcc@example.com"
    """
    logger.info("send_email: starting")

    try:
        from agent import config

        params = _parse_input(input)

        # Validate required fields
        missing = [f for f in ("to", "subject", "body") if not params.get(f)]
        if missing:
            return _err(f"Missing required fields: {', '.join(missing)}")

        to      = params["to"]
        subject = params["subject"]
        body    = params["body"]
        cc      = params.get("cc", "")
        bcc     = params.get("bcc", "")

        sender   = config.GMAIL_SENDER
        password = config.GMAIL_APP_PASSWORD

        if not sender or not password:
            return _err("GMAIL_SENDER or GMAIL_APP_PASSWORD not set in .env")

        # Build message
        msg            = MIMEMultipart()
        msg["From"]    = sender
        msg["To"]      = to
        msg["Subject"] = subject
        if cc:  msg["Cc"]  = cc
        if bcc: msg["Bcc"] = bcc
        msg.attach(MIMEText(body, "plain"))

        recipients = [r.strip() for r in [to, cc, bcc] if r]

        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())

        logger.info("send_email: success | to=%s | subject=%s", to, subject)
        return _ok(f"Email sent to {to} — Subject: '{subject}'")

    except smtplib.SMTPAuthenticationError:
        logger.error("send_email: Gmail authentication failed")
        return _err("Gmail auth failed. Check GMAIL_APP_PASSWORD in .env")

    except smtplib.SMTPException as e:
        logger.error("send_email: SMTP error: %s", e)
        return _err(f"SMTP error: {str(e)}")

    except Exception as e:
        logger.error("send_email: unexpected error: %s", e)
        return _err(f"Unexpected error: {str(e)}")


# ── Registry fragment ───────────────────────────────────────────────────────────

TOOLS = {
    "send_email": {
        "fn":          send_email,
        "description": (
            "Send an email via Gmail. "
            'Input JSON: {"to": "email@example.com", "subject": "...", "body": "..."}'
        ),
    },
}

