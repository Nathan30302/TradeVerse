"""
Outbound email for production hosts that block SMTP (e.g. Render free/starter).

Order of preference:
  1) Brevo HTTP API  (BREVO_API_KEY / SENDINBLUE_API_KEY) — works with a verified Gmail sender
  2) Resend HTTP API (RESEND_API_KEY) — best with a verified domain
  3) SMTP (MAIL_USERNAME + MAIL_PASSWORD) — often blocked on Render (ports 587/465)
"""

from __future__ import annotations

import logging
import re
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Optional, Tuple

from flask import current_app

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT_SEC = 12


def _env(*keys: str, default: str = "") -> str:
    import os

    for key in keys:
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            cfg = current_app.config.get(key)
            if cfg is not None and str(cfg).strip():
                raw = str(cfg).strip()
        if raw:
            # Render users often paste keys wrapped in quotes by accident.
            if (raw.startswith('"') and raw.endswith('"')) or (
                raw.startswith("'") and raw.endswith("'")
            ):
                raw = raw[1:-1].strip()
            return raw
    return default


def brevo_api_key() -> str:
    return _env("BREVO_API_KEY", "SENDINBLUE_API_KEY")


def resend_api_key() -> str:
    return _env("RESEND_API_KEY")


def smtp_configured() -> bool:
    return bool(_env("MAIL_USERNAME") and _env("MAIL_PASSWORD"))


def mail_is_configured() -> bool:
    """True if any outbound email backend is available."""
    return bool(brevo_api_key() or resend_api_key() or smtp_configured())


def preferred_backend() -> str:
    if brevo_api_key():
        return "brevo"
    if resend_api_key():
        return "resend"
    if smtp_configured():
        return "smtp"
    return "none"


def parse_sender(raw: str) -> Tuple[str, str]:
    """Return (display_name, email)."""
    name, addr = parseaddr(raw or "")
    if addr:
        return (name or "TradeVerse", addr)
    m = re.match(r"^(.+?)\s*<([^>]+)>$", (raw or "").strip())
    if m:
        return (m.group(1).strip().strip('"') or "TradeVerse", m.group(2).strip())
    bare = (raw or "").strip()
    if "@" in bare:
        return ("TradeVerse", bare)
    return ("TradeVerse", bare)


def default_from_address() -> Tuple[str, str]:
    raw = (
        _env("MAIL_DEFAULT_SENDER")
        or _env("MAIL_USERNAME")
        or _env("SUPPORT_EMAIL")
        or "noreply@tradeversejournal.space"
    )
    return parse_sender(raw)


def send_text_email(*, to_email: str, subject: str, body: str, from_raw: Optional[str] = None) -> bool:
    """
    Send a plain-text email. Prefers HTTPS APIs (Brevo/Resend) over SMTP.
    """
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        logger.error("send_text_email: invalid recipient")
        return False

    if from_raw:
        from_name, from_addr = parse_sender(from_raw)
    else:
        from_name, from_addr = default_from_address()

    backend = preferred_backend()
    if backend == "brevo":
        return _send_brevo(to_email, subject, body, from_name, from_addr)
    if backend == "resend":
        return _send_resend(to_email, subject, body, from_name, from_addr)
    if backend == "smtp":
        return _send_smtp(to_email, subject, body, from_name, from_addr)

    logger.warning(
        "No email backend configured. Set BREVO_API_KEY (recommended on Render) "
        "or RESEND_API_KEY, or MAIL_USERNAME/MAIL_PASSWORD for SMTP."
    )
    return False


def _send_brevo(to_email: str, subject: str, body: str, from_name: str, from_addr: str) -> bool:
    import requests

    key = brevo_api_key()
    payload = {
        "sender": {"name": from_name or "TradeVerse", "email": from_addr},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201, 202):
            return True
        logger.error("Brevo send failed status=%s body=%s", resp.status_code, resp.text[:500])
        return False
    except Exception:
        logger.exception("Brevo send failed to %s", to_email)
        return False


def _send_resend(to_email: str, subject: str, body: str, from_name: str, from_addr: str) -> bool:
    import requests

    key = resend_api_key()
    from_header = formataddr((from_name, from_addr)) if from_name else from_addr
    payload = {
        "from": from_header,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return True
        logger.error("Resend send failed status=%s body=%s", resp.status_code, resp.text[:500])
        return False
    except Exception:
        logger.exception("Resend send failed to %s", to_email)
        return False


def _send_smtp(to_email: str, subject: str, body: str, from_name: str, from_addr: str) -> bool:
    server = _env("MAIL_SERVER", default="smtp.gmail.com") or "smtp.gmail.com"
    try:
        port = int(_env("MAIL_PORT", default="587") or "587")
    except ValueError:
        port = 587
    use_tls = (_env("MAIL_USE_TLS", default="true") or "true").lower() in ("1", "true", "yes", "on")
    username = _env("MAIL_USERNAME")
    password = _env("MAIL_PASSWORD")
    from_header = formataddr((from_name, from_addr)) if from_name else from_addr

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_header
    msg["To"] = to_email

    try:
        with smtplib.SMTP(server, port, timeout=_SMTP_TIMEOUT_SEC) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(username, password)
            smtp.sendmail(from_addr, [to_email], msg.as_string())
        return True
    except OSError as e:
        # Render commonly blocks outbound SMTP (errno 101 Network unreachable).
        logger.error(
            "SMTP unreachable to %s:%s (%s). On Render, use BREVO_API_KEY or RESEND_API_KEY instead.",
            server,
            port,
            e,
        )
        return False
    except Exception:
        logger.exception("SMTP send failed to %s via %s:%s", to_email, server, port)
        return False
