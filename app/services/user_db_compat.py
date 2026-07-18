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
    "timezone, preferred_currency, theme, avatar_url, full_name, bio "
    "FROM users WHERE {where} LIMIT 1"
)

_DEFERRED_DEFAULTS = {
    "role": "user",
    "subscription_tier": "free",
    "subscription_status": "active",
    "exports_blocked": False,
    "ui_font": "jakarta",
}
_DEFERRED_NONE = (
    "trial_ends_at",
    "subscription_expires_at",
    "stripe_customer_id",
    "weekly_focus_rule",
    "weekly_focus_set_at",
    "signup_utm_source",
    "country_code",
    "phone_number",
)


def _stamp_missing_deferred_columns(UserModel, u, row_keys: set) -> None:
    """
    Prevent lazy SELECTs for deferred User columns that were not present in the compat row.

    Without this, accessing e.g. country_code on Postgres after a MIN/MID hydrate issues
    ``SELECT users.country_code ...`` and crashes if the column does not exist yet.

    ``set_committed_value`` expects the *string* attribute name (not the InstrumentedAttribute).
    """
    from sqlalchemy.orm.attributes import set_committed_value

    mapped_names = set()
    try:
        mapped_names = {p.key for p in UserModel.__mapper__.iterate_properties}
    except Exception:
        mapped_names = set(_DEFERRED_DEFAULTS) | set(_DEFERRED_NONE)

    def _stamp(name: str, value) -> None:
        if name not in mapped_names:
            return
        try:
            set_committed_value(u, name, value)
        except Exception:
            # Never let stamping break login after a successful row fetch.
            try:
                object.__setattr__(u, name, value)
            except Exception:
                pass

    for name, default in _DEFERRED_DEFAULTS.items():
        if name not in row_keys:
            _stamp(name, default)
    for name in _DEFERRED_NONE:
        if name not in row_keys:
            _stamp(name, None)


def stamp_omitted_user_columns(u, omit_cols=None) -> None:
    """
    Mark missing deferred User columns as loaded with safe defaults.

    Prevents SQLAlchemy from issuing ``SELECT users.role ...`` (etc.) when those
    columns are absent on a lagging production database.
    """
    if u is None:
        return
    try:
        from flask import current_app, has_app_context

        if omit_cols is None and has_app_context():
            omit_cols = (current_app.extensions.get("tradeverse_schema") or {}).get("omit_user_cols")
    except Exception:
        omit_cols = omit_cols
    omit_cols = set(omit_cols or ())
    if not omit_cols:
        return

    from sqlalchemy.orm.attributes import set_committed_value

    defaults = dict(_DEFERRED_DEFAULTS)
    for name in _DEFERRED_NONE:
        defaults.setdefault(name, None)

    for name in omit_cols:
        if name not in defaults and name not in _DEFERRED_DEFAULTS and name not in _DEFERRED_NONE:
            continue
        value = defaults.get(name)
        try:
            set_committed_value(u, name, value)
        except Exception:
            try:
                object.__setattr__(u, name, value)
            except Exception:
                pass


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
