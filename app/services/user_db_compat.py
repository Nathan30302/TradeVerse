"""
Hydrate User instances via raw SQL when full ORM loads fail (schema drift).

Used by Flask-Login and the login route so templates can read profile fields
without triggering lazy loads on incomplete instances.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

_FULL_SELECT = (
    "SELECT id, username, email, password_hash, is_active, is_verified, is_premium, "
    "timezone, preferred_currency, theme, created_at, last_login, avatar_url, full_name, bio, "
    "country_code, phone_number, role, subscription_tier, subscription_status, trial_ends_at, "
    "subscription_expires_at FROM users WHERE {where} LIMIT 1"
)

_MIN_SELECT = (
    "SELECT id, username, email, password_hash, is_active, is_verified, is_premium, "
    "timezone, preferred_currency, theme FROM users WHERE {where} LIMIT 1"
)


def hydrate_user_from_db(session, UserModel, *, user_id: int | None = None, username: str | None = None):
    """
    Return a User instance populated from a row, or None.

    Tries a wide SELECT first (enough for profile / subscription helpers), then a minimal SELECT.
    """
    if (user_id is None) == (username is None):
        raise ValueError("Provide exactly one of user_id or username")

    where = "id = :id" if user_id is not None else "username = :u"
    params = {"id": int(user_id)} if user_id is not None else {"u": username}

    for tmpl in (_FULL_SELECT, _MIN_SELECT):
        try:
            row = session.execute(text(tmpl.format(where=where)), params).mappings().first()
            if not row:
                return None
            u = UserModel()
            for k, v in row.items():
                setattr(u, k, v)
            return u
        except (OperationalError, ProgrammingError):
            try:
                session.rollback()
            except Exception:
                pass
            continue
    return None
