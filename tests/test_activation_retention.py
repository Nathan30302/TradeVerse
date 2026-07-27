"""Tests for playbook grade suggestions and retention nudges."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.playbook_grades import SUGGEST_MIN_TRADES, suggest_grade_from_trades
from app.services.retention_nudges import build_retention_nudge


def test_suggest_requires_min_trades():
    assert suggest_grade_from_trades(3.0, win_rate=55, count=SUGGEST_MIN_TRADES - 1) is None


def test_suggest_maps_rr_to_a_plus():
    s = suggest_grade_from_trades(3.1, win_rate=55, count=8)
    assert s is not None
    assert s["grade"] == "A+"
    assert s["differs_from_current"] is True


def test_suggest_matches_current():
    s = suggest_grade_from_trades(3.0, win_rate=60, count=10, current_grade="A+")
    assert s is not None
    assert s["differs_from_current"] is False


def test_idle_nudge(monkeypatch):
    monkeypatch.setattr(
        "app.services.retention_nudges.url_for",
        lambda endpoint, **kw: f"/{endpoint}",
    )
    now = datetime.now(timezone.utc)
    u = SimpleNamespace(
        last_login=now - timedelta(days=4),
        created_at=now - timedelta(days=40),
        weekly_focus_rule="Only A+ setups",
        weekly_focus_set_at=now - timedelta(days=2),
    )
    n = build_retention_nudge(u, review_queue={"total": 0})
    assert n is not None
    assert n["kind"] == "idle"


def test_eod_nudge_beats_focus(monkeypatch):
    monkeypatch.setattr(
        "app.services.retention_nudges.url_for",
        lambda endpoint, **kw: f"/{endpoint}",
    )
    now = datetime.now(timezone.utc)
    u = SimpleNamespace(
        last_login=now,
        created_at=now - timedelta(days=10),
        weekly_focus_rule="",
        weekly_focus_set_at=None,
    )
    n = build_retention_nudge(u, review_queue={"total": 2, "first_trade_id": 99})
    assert n["kind"] == "eod"
