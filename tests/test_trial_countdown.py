"""Per-user Pro Plus trial countdown (persisted trial_ends_at as source of truth)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.entitlements import (
    ensure_user_pro_plus_trial,
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
        id=1,
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


def test_days_remaining_follows_persisted_trial_end():
    now = datetime.now(timezone.utc)
    u = _user(created_at=now - timedelta(days=10), trial_ends_at=now + timedelta(days=50))
    left = get_trial_days_remaining(u)
    assert left is not None
    assert 49 <= left <= 51
    end = get_personal_trial_end(u)
    assert end is not None
    assert abs((end - (now + timedelta(days=50))).total_seconds()) < 2


def test_two_users_different_remaining():
    now = datetime.now(timezone.utc)
    early = _user(created_at=now - timedelta(days=20), trial_ends_at=now + timedelta(days=40))
    late = _user(created_at=now - timedelta(days=2), trial_ends_at=now + timedelta(days=58))
    assert get_trial_days_remaining(early) < get_trial_days_remaining(late)


def test_no_rolling_now_plus_sixty_without_ensure(monkeypatch):
    """Expired personal trial must not invent ~60 days in the getter alone."""
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
    if st.status == "trialing":
        left = get_trial_days_remaining(u)
        assert left is None or left < 60


def test_personal_trial_end_prefers_db_column():
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=5)
    stored = now + timedelta(days=55)
    u = _user(created_at=created, trial_ends_at=stored)
    end = get_personal_trial_end(u)
    assert end is not None
    assert abs((end - stored).total_seconds()) < 2


def test_ensure_repairs_expired_signup_clock_once():
    """May-era signup+60 (e.g. early July) gets a one-time now+60 repair."""
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=84)  # ~May when today is late July
    stale_end = created + timedelta(days=60)  # already past
    assert stale_end < now
    u = _user(
        created_at=created,
        trial_ends_at=stale_end,
        subscription_tier="pro",
        subscription_status="trialing",
    )
    assert ensure_user_pro_plus_trial(u) is True
    end = get_personal_trial_end(u)
    assert end is not None and end > now
    left = get_trial_days_remaining(u)
    assert left is not None and 59 <= left <= 60
    # Second ensure must not roll the clock forward again.
    first_end = end
    assert ensure_user_pro_plus_trial(u) is False
    assert abs((get_personal_trial_end(u) - first_end).total_seconds()) < 2


def test_ensure_skips_paid_active():
    now = datetime.now(timezone.utc)
    u = _user(
        created_at=now - timedelta(days=100),
        trial_ends_at=now - timedelta(days=40),
        subscription_tier="pro_plus",
        subscription_status="active",
        subscription_expires_at=now + timedelta(days=30),
    )
    assert ensure_user_pro_plus_trial(u) is False


def test_ensure_does_not_regrant_after_extended_trial_finished():
    """Users who already received a longer-than-signup grant and finished it stay done."""
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=200)
    # Extended grant ended 10 days ago (well past signup+60).
    u = _user(
        created_at=created,
        trial_ends_at=now - timedelta(days=10),
        subscription_tier="free",
        subscription_status="expired",
    )
    assert ensure_user_pro_plus_trial(u) is False


def test_days_remaining_matches_displayed_end_date():
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=42, hours=3)
    u = _user(created_at=now - timedelta(days=18), trial_ends_at=end)
    assert get_personal_trial_end(u) == end or abs((get_personal_trial_end(u) - end).total_seconds()) < 1
    left = get_trial_days_remaining(u)
    assert left == 43  # partial day rounds up
