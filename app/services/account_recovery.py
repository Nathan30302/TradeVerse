"""
Account recovery helpers: timed reset tokens + recovery emails.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from flask import current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

_SALT = "tradeverse-password-reset-v1"
_DEFAULT_MAX_AGE = 3600  # 1 hour


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


def send_recovery_email(user, *, reset_token: str) -> bool:
    """
    Email username reminder + password reset link.

    Returns True if send appeared to succeed.
    """
    from flask_mail import Message
    from app import mail

    if not mail_is_configured():
        logger.warning("Recovery email skipped: MAIL_USERNAME/MAIL_PASSWORD not configured")
        return False

    sender = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME")
    support = current_app.config.get("SUPPORT_EMAIL") or sender
    origin = public_site_origin()
    try:
        reset_path = url_for("auth.reset_password", token=reset_token)
    except Exception:
        reset_path = f"/auth/reset-password/{reset_token}"
    reset_url = f"{origin}{reset_path}" if origin else reset_path

    app_name = current_app.config.get("APP_NAME") or "TradeVerse"
    username = user.username or "trader"
    email = user.email

    msg = Message(
        subject=f"{app_name}: reset your password",
        sender=sender,
        recipients=[email],
    )
    msg.body = "\n".join(
        [
            f"Hi {username},",
            "",
            f"We received a request to recover your {app_name} account.",
            "",
            f"Your username is: {username}",
            "",
            "Reset your password using this link (expires in about 1 hour):",
            reset_url,
            "",
            "If you did not request this, you can ignore this email — your password stays the same.",
            "",
            f"Need help? Write to {support}",
            "",
            f"— {app_name}",
        ]
    )
    try:
        mail.send(msg)
        return True
    except Exception:
        logger.exception("Failed to send recovery email to %s", email)
        return False
