"""Per-user Pro Plus trial countdown (signup-anchored, not rolling now+60)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import os

import pytest

from app.services.entitlements import (
    get_effective_subscription_state,
    get_personal_trial_end,
    get_trial_days_remaining,
)


@pytest.fixture(autouse=True)
def _promo_env(monkeypatch):
    monkeypatch.setenv("TV_ALL_USERS_PROPLUS_TRIAL", "1")
    monkeypatch.setenv("TV_ALL_USERS_PROPLUS_TRIAL_DAYS", "60")
    monkeypatch.setenv("TV_TRIAL_DAYS_PRO_PLUS", "60")
    monkeypatch.delenv("TV_PROMO_ACCESS_UNTIL", raising=False)


def _user(**kwargs):
    now = datetime.now(timezone.utc)
    defaults = dict(
        subscription_tier="pro_plus",
        subscription_status="trialing",
        role="user",
        created_at=now - timedelta(days=10),
        trial_ends_at=now + timedelta(days=50),
        subscription_expires_at=None,
        email="t@example.com",
        username="trader",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_days_remaining_declines_from_signup():
    now = datetime.now(timezone.utc)
    u = _user(created_at=now - timedelta(days=10), trial_ends_at=now + timedelta(days=999))
    # Inflated trial_ends_at must not freeze the clock — signup+60 → ~50 left
    left = get_trial_days_remaining(u)
    assert left is not None
    assert 49 <= left <= 51


def test_two_users_different_remaining():
    now = datetime.now(timezone.utc)
    early = _user(created_at=now - timedelta(days=20), trial_ends_at=now + timedelta(days=40))
    late = _user(created_at=now - timedelta(days=2), trial_ends_at=now + timedelta(days=58))
    assert get_trial_days_remaining(early) < get_trial_days_remaining(late)


def test_no_rolling_now_plus_sixty_for_old_accounts(monkeypatch):
    """Expired personal trial must not show ~60 forever via now+60."""
    monkeypatch.setenv("TV_ALL_USERS_PROPLUS_TRIAL", "1")
    monkeypatch.delenv("TV_PROMO_ACCESS_UNTIL", raising=False)
    now = datetime.now(timezone.utc)
    u = _user(
        created_at=now - timedelta(days=90),
        trial_ends_at=now - timedelta(days=30),
        subscription_tier="free",
        subscription_status="active",
    )
    st = get_effective_subscription_state(u)
    # Without promo_until, expired personal trial should not invent a fresh 60-day window.
    if st.status == "trialing":
        left = get_trial_days_remaining(u)
        assert left is None or left < 60


def test_personal_trial_end_is_signup_plus_days():
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=5)
    u = _user(created_at=created, trial_ends_at=now + timedelta(days=100))
    end = get_personal_trial_end(u)
    assert end is not None
    assert abs((end - (created + timedelta(days=60))).total_seconds()) < 2
