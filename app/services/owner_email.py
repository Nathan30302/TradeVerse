"""
Owner console: plain-text email helpers (placeholders + audience lists).
"""

from __future__ import annotations

from datetime import timedelta
from app.utils.timeutil import utc_now
from typing import List

from sqlalchemy import func

from app.models.user import User


def apply_email_placeholders(
    text: str,
    *,
    user: User,
    app_name: str,
    login_url: str,
) -> str:
    """Replace {username}, {email}, {app_name}, {login_url} in a template string."""
    u = user
    return (
        (text or "")
        .replace("{username}", (getattr(u, "username", None) or "trader"))
        .replace("{email}", (getattr(u, "email", None) or ""))
        .replace("{app_name}", app_name)
        .replace("{login_url}", login_url)
    )


def mail_sender_address(app_config: dict) -> str | None:
    """Resolve From address for transactional/bulk mail."""
    return (app_config.get("MAIL_DEFAULT_SENDER") or app_config.get("MAIL_USERNAME") or "").strip() or None


def mail_is_configured(app_config: dict) -> bool:
    return bool(
        app_config.get("MAIL_USERNAME")
        and app_config.get("MAIL_PASSWORD")
        and mail_sender_address(app_config)
    )


def audience_users(*, audience: str, inactive_days: int) -> List[User]:
    """
    Return users eligible for bulk send (active accounts with an email address).

    audience:
      - all_registered: every active user with email
      - inactive: active users whose last activity is older than inactive_days
    """
    base = User.query.filter(
        User.is_active.is_(True),
        User.email.isnot(None),
        User.email != "",
    )

    if audience == "all_registered":
        return base.order_by(User.id.asc()).all()

    if audience == "inactive":
        cutoff = utc_now() - timedelta(days=max(1, int(inactive_days)))
        activity = func.coalesce(User.last_login, User.created_at)
        return (
            base.filter(activity.isnot(None), activity < cutoff)
            .order_by(User.id.asc())
            .all()
        )

    return []
