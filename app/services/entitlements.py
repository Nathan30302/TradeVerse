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

T = TypeVar("T")


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
    tier = (getattr(user, "subscription_tier", None) or "free").lower()
    status = (getattr(user, "subscription_status", None) or "active").lower()

    now = _utcnow()
    trial_ends_at: Optional[datetime] = getattr(user, "trial_ends_at", None)
    subscription_expires_at: Optional[datetime] = getattr(user, "subscription_expires_at", None)

    if tier == "free":
        return SubscriptionState(tier="free", status="active", is_active=True)

    if trial_ends_at and trial_ends_at >= now:
        return SubscriptionState(tier=tier, status="trialing", is_active=True)

    if subscription_expires_at and subscription_expires_at < now:
        return SubscriptionState(tier=tier, status="expired", is_active=False)

    if status in {"active", "trialing"}:
        return SubscriptionState(tier=tier, status=status, is_active=True)

    if status in {"past_due"}:
        return SubscriptionState(tier=tier, status="past_due", is_active=False)

    if status in {"canceled", "cancelled"}:
        return SubscriptionState(tier=tier, status="canceled", is_active=False)

    return SubscriptionState(tier=tier, status=status, is_active=False)


def user_has_feature(user, feature: str) -> bool:
    state = get_effective_subscription_state(user)
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

