"""
Entitlements and subscription state helpers.

This module centralizes feature gating logic so routes/templates don't need to
manually reason about tiers/statuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from functools import wraps
from typing import Callable, Dict, Iterable, Optional, Set, TypeVar

from flask import abort, jsonify, request
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
        "coach_mode",
    },
    "pro_plus": {
        "basic_analytics",
        "advanced_analytics",
        "exports",
        "broker_api_import",
        "coach_mode",
        "ai_web",
    },
    "elite": {
        "basic_analytics",
        "advanced_analytics",
        "exports",
        "broker_api_import",
        "coach_mode",
        "ai_web",
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

def _as_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Normalize DB datetimes for safe comparisons.

    Our DB stores naive UTC datetimes in several columns. Flask/Python comparisons
    will raise if we compare naive to timezone-aware.
    """
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_promo_access_until() -> Optional[datetime]:
    """Optional global promo end (ISO date/datetime). Applies to current and new users."""
    raw = (os.environ.get("TV_PROMO_ACCESS_UNTIL") or "").strip()
    if not raw:
        return None
    try:
        # Allow date-only (YYYY-MM-DD) or full ISO
        if len(raw) <= 10:
            raw = raw + "T23:59:59+00:00"
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return _as_utc_aware(dt)
    except ValueError:
        return None


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
    trial_ends_at: Optional[datetime] = _as_utc_aware(_safe_getattr(user, "trial_ends_at", None))
    subscription_expires_at: Optional[datetime] = _as_utc_aware(_safe_getattr(user, "subscription_expires_at", None))

    # Marketing mode: give everyone Pro Plus features for a limited time.
    # This avoids forcing immediate payment setup and keeps the platform fully usable.
    #
    # Turn off by setting: TV_ALL_USERS_PROPLUS_TRIAL=0
    # Optional hard end date (ISO): TV_PROMO_ACCESS_UNTIL=2026-09-15T00:00:00+00:00
    #   — current + new users stay on Pro Plus until that date regardless of old trial_ends_at.
    force_all_trial = (os.environ.get("TV_ALL_USERS_PROPLUS_TRIAL", "1") or "1").strip().lower() in {"1", "true", "yes", "on"}
    if force_all_trial:
        days = int(os.environ.get("TV_ALL_USERS_PROPLUS_TRIAL_DAYS", "60") or "60")
        created = _as_utc_aware(_safe_getattr(user, "created_at", None)) or now
        promo_until = _parse_promo_access_until()
        candidates = []
        if promo_until:
            candidates.append(promo_until)
        if trial_ends_at:
            candidates.append(trial_ends_at)
        else:
            candidates.append(created + timedelta(days=days))
        trial_end = max(candidates) if candidates else (created + timedelta(days=days))
        if trial_end >= now:
            return SubscriptionState(
                tier="pro_plus",
                status="trialing",
                is_active=True,
                trial_ends_at=trial_end,
                subscription_expires_at=None,
            )
        # Marketing trial window elapsed — use normal tier logic below.

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


def get_trial_days_remaining(user) -> Optional[int]:
    """Whole calendar days left in the effective trial, or None if not trialing."""
    st = get_effective_subscription_state(user)
    if st.status != "trialing" or not st.trial_ends_at:
        return None
    end = _as_utc_aware(st.trial_ends_at)
    if not end:
        return None
    delta = end - _utcnow()
    return max(0, int(delta.total_seconds() // 86400))


def user_has_feature(user, feature: str) -> bool:
    state = get_effective_subscription_state(user)
    if state.tier == "owner":
        return True
    allowed = FEATURES_BY_TIER.get(state.tier, FEATURES_BY_TIER["free"])
    return state.is_active and feature in allowed


def _feature_locked_response(feature: str):
    """JSON for API/fetch callers; 404 HTML for normal page views."""
    wants_json = (
        request.path.startswith('/api/')
        or '/api/' in request.path
        or request.is_json
        or request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
    )
    if wants_json:
        return jsonify({'success': False, 'error': 'feature_locked', 'feature': feature}), 403
    abort(404)


def require_feature(feature: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Route decorator. HTML views get 404; JSON/API callers get 403 with feature_locked.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapped(*args, **kwargs):  # type: ignore[misc]
            if not current_user.is_authenticated:
                abort(401)
            if not user_has_feature(current_user, feature):
                return _feature_locked_response(feature)
            return fn(*args, **kwargs)

        return wrapped

    return decorator

