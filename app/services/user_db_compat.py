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

# Prod DBs upgraded for billing/subscription but not yet for country/phone (e.g. migration order lag).
_MID_SELECT = (
    "SELECT id, username, email, password_hash, is_active, is_verified, is_premium, "
    "timezone, preferred_currency, theme, created_at, last_login, avatar_url, full_name, bio, "
    "role, subscription_tier, subscription_status, trial_ends_at, subscription_expires_at "
    "FROM users WHERE {where} LIMIT 1"
)

_MIN_SELECT = (
    "SELECT id, username, email, password_hash, is_active, is_verified, is_premium, "
    "timezone, preferred_currency, theme FROM users WHERE {where} LIMIT 1"
)

_DEFERRED_DEFAULTS = {
    "role": "user",
    "subscription_tier": "free",
    "subscription_status": "active",
    "exports_blocked": False,
}
_DEFERRED_NONE = (
    "trial_ends_at",
    "subscription_expires_at",
    "stripe_customer_id",
    "weekly_focus_rule",
    "signup_utm_source",
    "country_code",
    "phone_number",
)


def _stamp_missing_deferred_columns(UserModel, u, row_keys: set) -> None:
    """
    Prevent lazy SELECTs for deferred User columns that were not present in the compat row.

    Without this, accessing e.g. country_code on Postgres after a MIN/MID hydrate issues
    ``SELECT users.country_code ...`` and crashes if the column does not exist yet.
    """
    from sqlalchemy.orm.attributes import set_committed_value

    for name, default in _DEFERRED_DEFAULTS.items():
        if name not in row_keys:
            set_committed_value(u, getattr(UserModel, name), default)
    for name in _DEFERRED_NONE:
        if name not in row_keys:
            set_committed_value(u, getattr(UserModel, name), None)


def hydrate_user_from_db(session, UserModel, *, user_id: int | None = None, username: str | None = None):
    """
    Return a User instance populated from a row, or None.

    Tries a wide SELECT first (enough for profile / subscription helpers), then a minimal SELECT.
    """
    if (user_id is None) == (username is None):
        raise ValueError("Provide exactly one of user_id or username")

    where = "id = :id" if user_id is not None else "username = :u"
    params = {"id": int(user_id)} if user_id is not None else {"u": username}

    for tmpl in (_FULL_SELECT, _MID_SELECT, _MIN_SELECT):
        try:
            row = session.execute(text(tmpl.format(where=where)), params).mappings().first()
            if not row:
                return None
            u = UserModel()
            keys = set()
            for k, v in row.items():
                setattr(u, k, v)
                keys.add(k)
            _stamp_missing_deferred_columns(UserModel, u, keys)
            return u
        except (OperationalError, ProgrammingError):
            try:
                session.rollback()
            except Exception:
                pass
            continue
    return None
