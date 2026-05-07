"""
Entitlements and subscription state helpers.

This module centralizes feature gating logic so routes/templates don't need to
manually reason about tiers/statuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from typing import Callable, Dict, Iterable, Optional, Set, TypeVar

from flask import abort
from flask_login import current_user
import os

T = TypeVar("T")

def _parse_csv_env(name: str) -> Set[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return set()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def is_owner_user(user) -> bool:
    """
    Secure owner bypass based on environment allowlist.

    Configure ONE of:
      - OWNER_EMAILS="owner@example.com,other@example.com"
      - OWNER_USERNAMES="admin,founder"
    """
    if not user:
        return False
    owner_emails = _parse_csv_env("OWNER_EMAILS")
    owner_usernames = _parse_csv_env("OWNER_USERNAMES")
    if not owner_emails and not owner_usernames:
        return False
    email = (_safe_getattr(user, "email", None) or "").strip().lower()
    username = (_safe_getattr(user, "username", None) or "").strip().lower()
    return (email in owner_emails) or (username in owner_usernames)
def _safe_getattr(user, name: str, default=None):
    try:
        return getattr(user, name, default)
    except Exception:
        # If a deferred column is missing in the DB (schema drift), SQLAlchemy can
        # abort the current transaction. Roll back to keep the request usable.
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return default


FEATURES_BY_TIER: Dict[str, Set[str]] = {
    "free": {
        "basic_analytics",
    },
    "pro": {
        "basic_analytics",
        "advanced_analytics",
        "exports",
        "broker_api_import",
    },
    "pro_plus": {
        "basic_analytics",
        "advanced_analytics",
        "exports",
        "broker_api_import",
        "coach_mode",
    },
    "elite": {
        "basic_analytics",
        "advanced_analytics",
        "exports",
        "broker_api_import",
        "coach_mode",
    },
}


@dataclass(frozen=True)
class SubscriptionState:
    tier: str
    status: str  # active, trialing, past_due, canceled, expired
    is_active: bool
    trial_ends_at: Optional[datetime] = None
    subscription_expires_at: Optional[datetime] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_effective_subscription_state(user) -> SubscriptionState:
    """
    Compute an effective state based on persisted columns.

    - If tier is free -> active
    - If trial_ends_at in the future -> trialing
    - If subscription_status is not active -> not active
    - If subscription_expires_at is set and in the past -> expired
    """
    tier = (_safe_getattr(user, "subscription_tier", None) or "free").lower()
    status = (_safe_getattr(user, "subscription_status", None) or "active").lower()
    role = (_safe_getattr(user, "role", None) or "user").lower()

    now = _utcnow()
    trial_ends_at: Optional[datetime] = _safe_getattr(user, "trial_ends_at", None)
    subscription_expires_at: Optional[datetime] = _safe_getattr(user, "subscription_expires_at", None)

    # Owner/admin bypass: full access without billing enforcement.
    if role in {"owner"} or is_owner_user(user):
        return SubscriptionState(tier="owner", status="active", is_active=True, trial_ends_at=None, subscription_expires_at=None)

    if tier == "free":
        return SubscriptionState(tier="free", status="active", is_active=True, trial_ends_at=trial_ends_at, subscription_expires_at=subscription_expires_at)

    if trial_ends_at and trial_ends_at >= now:
        return SubscriptionState(tier=tier, status="trialing", is_active=True, trial_ends_at=trial_ends_at, subscription_expires_at=subscription_expires_at)

    if subscription_expires_at and subscription_expires_at < now:
        return SubscriptionState(tier=tier, status="expired", is_active=False, trial_ends_at=trial_ends_at, subscription_expires_at=subscription_expires_at)

    if status in {"active", "trialing"}:
        return SubscriptionState(tier=tier, status=status, is_active=True, trial_ends_at=trial_ends_at, subscription_expires_at=subscription_expires_at)

    if status in {"past_due"}:
        return SubscriptionState(tier=tier, status="past_due", is_active=False, trial_ends_at=trial_ends_at, subscription_expires_at=subscription_expires_at)

    if status in {"canceled", "cancelled"}:
        return SubscriptionState(tier=tier, status="canceled", is_active=False, trial_ends_at=trial_ends_at, subscription_expires_at=subscription_expires_at)

    return SubscriptionState(tier=tier, status=status, is_active=False, trial_ends_at=trial_ends_at, subscription_expires_at=subscription_expires_at)


def user_has_feature(user, feature: str) -> bool:
    state = get_effective_subscription_state(user)
    if state.tier == "owner":
        return True
    allowed = FEATURES_BY_TIER.get(state.tier, FEATURES_BY_TIER["free"])
    return state.is_active and feature in allowed


def require_feature(feature: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Route decorator. Returns 404 (not 403) to avoid leaking premium endpoints.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapped(*args, **kwargs):  # type: ignore[misc]
            if not current_user.is_authenticated:
                abort(401)
            if not user_has_feature(current_user, feature):
                abort(404)
            return fn(*args, **kwargs)

        return wrapped

    return decorator

