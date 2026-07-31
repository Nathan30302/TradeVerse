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


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def trial_period_days() -> int:
    """Configured Pro Plus trial length (default 60)."""
    raw = os.environ.get("TV_TRIAL_DAYS_PRO_PLUS") or os.environ.get("TV_ALL_USERS_PROPLUS_TRIAL_DAYS") or "60"
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = 60
    return max(1, min(days, 366))


def all_users_trial_days() -> int:
    """Length used for the all-users marketing trial clock (default 60)."""
    raw = os.environ.get("TV_ALL_USERS_PROPLUS_TRIAL_DAYS") or os.environ.get("TV_TRIAL_DAYS_PRO_PLUS") or "60"
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = 60
    return max(1, min(days, 366))


def is_all_users_proplus_trial_enabled() -> bool:
    """Marketing overlay: eligible accounts get Pro Plus while their personal trial is open."""
    return _env_flag("TV_ALL_USERS_PROPLUS_TRIAL", "1")


def _signup_trial_end(user, days: Optional[int] = None) -> Optional[datetime]:
    """created_at + N (UTC), or None when created_at is missing."""
    created = _as_utc_aware(_safe_getattr(user, "created_at", None))
    if created is None:
        return None
    return created + timedelta(days=days if days is not None else all_users_trial_days())


def _is_paid_active(user, now: Optional[datetime] = None) -> bool:
    """True for paying Pro/Pro Plus customers (do not overlay marketing trial)."""
    now = now or _utcnow()
    tier = (_safe_getattr(user, "subscription_tier", None) or "free").lower()
    status = (_safe_getattr(user, "subscription_status", None) or "active").lower()
    subscription_expires_at = _as_utc_aware(_safe_getattr(user, "subscription_expires_at", None))
    return (
        status == "active"
        and tier in {"pro", "pro_plus"}
        and (subscription_expires_at is None or subscription_expires_at >= now)
    )


def _naive_utc(dt: datetime) -> datetime:
    """Store naive UTC in DB columns that historically omit tzinfo."""
    aware = _as_utc_aware(dt) or dt
    return aware.replace(tzinfo=None)


def ensure_user_pro_plus_trial(user) -> bool:
    """
    Persist a correct Pro Plus trial window for eligible users.

    Returns True if the user row was modified (caller should commit).

    Policy (when TV_ALL_USERS_PROPLUS_TRIAL is on):
      - Source of truth for countdown/UI is persisted ``trial_ends_at``.
      - Recent accounts: ``trial_ends_at = created_at + N`` (N default 60).
      - Accounts whose signup+N window already elapsed and who only ever had that
        signup-anchored end (or no end): one-time repair to ``now + N``.
        This fixes stuck July end dates for May-era signups without rolling forever.
      - After a longer-than-signup grant expires, do NOT grant again.
      - Never touch owners or paid active Pro/Pro Plus subscribers.

    When the marketing overlay is off, only heal trialing rows that lack a future end.
    """
    if not user or not _safe_getattr(user, "id", None):
        return False

    role = (_safe_getattr(user, "role", None) or "user").lower()
    if role == "owner" or is_owner_user(user):
        return False

    now = _utcnow()
    if _is_paid_active(user, now):
        return False

    days = all_users_trial_days()
    signup_end = _signup_trial_end(user, days)
    trial_ends_at = _as_utc_aware(_safe_getattr(user, "trial_ends_at", None))
    status = (_safe_getattr(user, "subscription_status", None) or "active").lower()
    tier = (_safe_getattr(user, "subscription_tier", None) or "free").lower()
    force_all = is_all_users_proplus_trial_enabled()

    desired_end: Optional[datetime] = None

    if trial_ends_at and trial_ends_at >= now:
        # Keep a valid future grant; optionally extend a short leftover (e.g. 14-day)
        # up to the full signup window while that window is still open.
        desired_end = trial_ends_at
        if force_all and signup_end and signup_end > trial_ends_at:
            desired_end = signup_end
    elif force_all:
        if signup_end and signup_end >= now:
            desired_end = signup_end
        else:
            # Signup clock already finished. One-time fresh grant only when the
            # stored end never went beyond signup+N (or was never set).
            skew = timedelta(days=1)
            only_had_signup_clock = (
                trial_ends_at is None
                or signup_end is None
                or trial_ends_at <= (signup_end + skew)
            )
            if only_had_signup_clock:
                desired_end = now + timedelta(days=days)
    elif status == "trialing":
        # Overlay off, but row still says trialing without a usable end — heal once.
        if signup_end and signup_end >= now:
            desired_end = signup_end
        else:
            desired_end = now + timedelta(days=days)

    if desired_end is None:
        return False

    changed = False
    # Compare with 60s tolerance so we don't rewrite identical timestamps forever.
    if trial_ends_at is None or abs((desired_end - trial_ends_at).total_seconds()) > 60:
        try:
            user.trial_ends_at = _naive_utc(desired_end)
            changed = True
        except Exception:
            return False

    if force_all or status == "trialing":
        if tier != "pro_plus":
            try:
                user.subscription_tier = "pro_plus"
                changed = True
            except Exception:
                pass
        if status != "trialing":
            try:
                user.subscription_status = "trialing"
                changed = True
            except Exception:
                pass
        try:
            if _safe_getattr(user, "subscription_expires_at", None) is not None:
                user.subscription_expires_at = None
                changed = True
        except Exception:
            pass

    return changed


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

    # Owner/admin bypass: full access without billing enforcement (check before promo trial).
    if role in {"owner"} or is_owner_user(user):
        return SubscriptionState(tier="owner", status="active", is_active=True, trial_ends_at=None, subscription_expires_at=None)

    # Paying customers keep their paid plan — do not overlay the marketing trial.
    is_paid_active = _is_paid_active(user, now)

    # Marketing mode: give everyone Pro Plus features for a limited time.
    # This avoids forcing immediate payment setup and keeps the platform fully usable.
    #
    # Turn off by setting: TV_ALL_USERS_PROPLUS_TRIAL=0
    # Optional hard end date (ISO): TV_PROMO_ACCESS_UNTIL=2026-09-15T00:00:00+00:00
    #   — feature access may continue until that date, but the visible countdown
    #     prefers each user's persisted trial_ends_at (see get_personal_trial_end).
    force_all_trial = is_all_users_proplus_trial_enabled()
    if force_all_trial and not is_paid_active:
        days = all_users_trial_days()
        signup_end = _signup_trial_end(user, days)
        promo_until = _parse_promo_access_until()

        # Prefer persisted trial_ends_at (repaired grant or signup grant). Fall back
        # to signup+N only while that window is still open — never invent now+N here
        # (that belongs in ensure_user_pro_plus_trial so the clock can decline).
        if trial_ends_at and trial_ends_at >= now:
            personal_end = trial_ends_at
        elif signup_end and signup_end >= now:
            personal_end = signup_end
        else:
            personal_end = None

        if personal_end is not None and personal_end >= now:
            return SubscriptionState(
                tier="pro_plus",
                status="trialing",
                is_active=True,
                trial_ends_at=personal_end,
                subscription_expires_at=None,
            )
        # Personal trial finished — optional global promo can still unlock features,
        # but do not pretend the user still has a fresh 60-day personal trial.
        if promo_until and promo_until >= now:
            return SubscriptionState(
                tier="pro_plus",
                status="trialing",
                is_active=True,
                trial_ends_at=promo_until,
                subscription_expires_at=None,
            )
        # Marketing trial window elapsed — use normal tier logic below.

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


def get_personal_trial_end(user) -> Optional[datetime]:
    """
    This user's trial end for UI countdown (single source of truth with days left).

    Prefer persisted ``trial_ends_at`` (including one-time repairs from
    ``ensure_user_pro_plus_trial``). Fall back to ``created_at + trial days`` when
    the DB column is empty so new/partial rows still show a coherent end date.
    """
    trial_ends_at = _as_utc_aware(_safe_getattr(user, "trial_ends_at", None))
    if trial_ends_at is not None:
        return trial_ends_at

    days = trial_period_days()
    created = _as_utc_aware(_safe_getattr(user, "created_at", None))
    if created is not None:
        return created + timedelta(days=days)
    return None


def get_trial_days_remaining(user) -> Optional[int]:
    """Whole calendar days left on THIS user's trial clock, or None if not trialing."""
    st = get_effective_subscription_state(user)
    if st.status != "trialing":
        return None

    # Same end date the templates show (trial_personal_ends_at / sub.trial_ends_at).
    end = get_personal_trial_end(user)
    now = _utcnow()
    if end is None or end < now:
        end = _as_utc_aware(st.trial_ends_at)
    if not end:
        return None
    delta = end - now
    secs = delta.total_seconds()
    if secs <= 0:
        return 0
    # Round up partial days so "23 hours left" shows as 1 day, not 0.
    return max(1, int((secs + 86399) // 86400))


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
