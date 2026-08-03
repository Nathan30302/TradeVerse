"""
Account recovery helpers: timed reset tokens + recovery emails.
"""

from __future__ import annotations

import logging
import re
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Optional, Tuple, Union

from flask import current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

_SALT = "tradeverse-password-reset-v1"
_DEFAULT_MAX_AGE = 3600  # 1 hour
_SMTP_TIMEOUT_SEC = 12


def _serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY") or "dev-insecure"
    return URLSafeTimedSerializer(secret_key=secret, salt=_SALT)


def make_reset_token(user) -> str:
    """Create a one-time-ish password reset token bound to user id + password hash prefix."""
    pwd = getattr(user, "password_hash", None) or ""
    payload = {
        "uid": int(user.id),
        "email": (user.email or "").strip().lower(),
        "ph": pwd[:20],
    }
    return _serializer().dumps(payload)


def load_reset_token(token: str, *, max_age: Optional[int] = None) -> Tuple[Optional[dict], Optional[str]]:
    """
    Validate token.

    Returns (payload, error_message). payload is None on failure.
    """
    age = max_age if max_age is not None else int(
        current_app.config.get("PASSWORD_RESET_MAX_AGE", _DEFAULT_MAX_AGE) or _DEFAULT_MAX_AGE
    )
    try:
        data = _serializer().loads(token, max_age=age)
    except SignatureExpired:
        return None, "This reset link has expired. Request a new one."
    except BadSignature:
        return None, "This reset link is invalid. Request a new one."
    if not isinstance(data, dict) or "uid" not in data:
        return None, "This reset link is invalid. Request a new one."
    return data, None


def public_site_origin() -> str:
    """Absolute site origin for email links."""
    configured = (current_app.config.get("PUBLIC_SITE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    try:
        from flask import request

        return (request.url_root or "").rstrip("/")
    except Exception:
        return ""


def mail_is_configured() -> bool:
    return bool(
        current_app.config.get("MAIL_USERNAME")
        and current_app.config.get("MAIL_PASSWORD")
        and (current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME"))
    )


def _sender_header(raw: str) -> str:
    """Normalize 'Name <email>' or bare email into an RFC From header."""
    name, addr = parseaddr(raw or "")
    if addr:
        return formataddr((name, addr)) if name else addr
    # Fallback if parseaddr fails on odd values
    m = re.match(r"^(.+?)\s*<([^>]+)>$", (raw or "").strip())
    if m:
        return formataddr((m.group(1).strip().strip('"'), m.group(2).strip()))
    return (raw or "").strip()


def send_recovery_email(user, *, reset_token: str) -> bool:
    """
    Email username reminder + password reset link.

    Uses smtplib with a short timeout so a stuck Gmail connection cannot
    take down the request worker (which showed up as Internal Server Error).
    """
    if not mail_is_configured():
        logger.warning("Recovery email skipped: MAIL_USERNAME/MAIL_PASSWORD not configured")
        return False

    server = (current_app.config.get("MAIL_SERVER") or "smtp.gmail.com").strip()
    try:
        port = int(current_app.config.get("MAIL_PORT") or 587)
    except (TypeError, ValueError):
        port = 587
    use_tls = bool(current_app.config.get("MAIL_USE_TLS", True))
    username = (current_app.config.get("MAIL_USERNAME") or "").strip()
    password = current_app.config.get("MAIL_PASSWORD") or ""
    sender_raw = (
        current_app.config.get("MAIL_DEFAULT_SENDER")
        or current_app.config.get("MAIL_USERNAME")
        or ""
    )
    from_header = _sender_header(str(sender_raw))
    _, from_addr = parseaddr(from_header)
    if not from_addr:
        from_addr = username

    support = current_app.config.get("SUPPORT_EMAIL") or from_addr
    origin = public_site_origin()
    try:
        reset_path = url_for("auth.reset_password", token=reset_token, _external=False)
    except Exception:
        reset_path = f"/auth/reset-password/{reset_token}"
    reset_url = f"{origin}{reset_path}" if origin else reset_path

    app_name = current_app.config.get("APP_NAME") or "TradeVerse"
    uname = getattr(user, "username", None) or "trader"
    to_email = (getattr(user, "email", None) or "").strip()
    if not to_email:
        logger.error("Recovery email aborted: user has no email")
        return False

    body = "\n".join(
        [
            f"Hi {uname},",
            "",
            f"You asked to recover your {app_name} account. Here's the easy path:",
            "",
            f"1) Your username is: {uname}",
            "2) Tap this link to set a new password (expires in about 1 hour):",
            reset_url,
            "3) Sign in with your username (or this email) and the new password.",
            "",
            "After you sign in, open Settings to change your username if you want.",
            "",
            "If you did not request this, ignore this email — your password stays the same.",
            "",
            f"Need help? Write to {support}",
            "",
            f"— {app_name}",
        ]
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"{app_name}: reset your password"
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
    except Exception:
        logger.exception(
            "Failed to send recovery email to %s via %s:%s",
            to_email,
            server,
            port,
        )
        return False
