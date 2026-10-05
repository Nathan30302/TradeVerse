"""Owner Rules Desk — personal discipline coach (owner-only)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import create_app, db, schema_compat
from app.models.owner_rules import OwnerRulebook
from app.models.user import User
from app.services.owner_discipline import (
    advise_before_trade,
    build_multi_tf_brief,
    drawdown_fraction,
    is_owner_discipline_user,
    session_gate,
    suggested_risk,
    windows_from_form,
)


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(application)
        owner = User(username="nathan", email="nathan@example.com")
        owner.set_password("password12")
        owner.role = "owner"
        user = User(username="trader", email="trader@example.com")
        user.set_password("password12")
        user.role = "user"
        db.session.add_all([owner, user])
        db.session.commit()
        yield application


@pytest.fixture
def owner_client(app):
    c = app.test_client()
    c.post("/auth/login", data={"username": "nathan", "password": "password12"}, follow_redirects=True)
    return c


@pytest.fixture
def user_client(app):
    c = app.test_client()
    c.post("/auth/login", data={"username": "trader", "password": "password12"}, follow_redirects=True)
    return c


def test_only_owner_sees_rules_desk(app):
    c = app.test_client()
    c.post("/auth/login", data={"username": "nathan", "password": "password12"}, follow_redirects=True)
    assert c.get("/owner/rules/").status_code == 200
    c.get("/auth/logout", follow_redirects=True)
    c.post("/auth/login", data={"username": "trader", "password": "password12"}, follow_redirects=True)
    with c.session_transaction() as sess:
        uid = sess.get("_user_id")
    with app.app_context():
        u = User.query.get(int(uid))
        assert u.username == "trader"
        assert (u.role or "").lower() == "user"
    assert c.get("/owner/rules/").status_code == 404


def test_risk_scales_down_in_drawdown():
    book = SimpleNamespace(
        risk_base_pct=1.0,
        risk_min_pct=0.25,
        account_starting_balance=10000,
        account_high_water=10000,
        account_current_balance=7500,  # 25% DD
    )
    assert drawdown_fraction(book) == pytest.approx(0.25)
    risk = suggested_risk(book)
    assert risk["mode"] == "recovery"
    assert risk["risk_pct"] == pytest.approx(0.25)


def test_session_windows_parse_and_gate():
    js = windows_from_form("London|0,1,2,3,4|00:00|23:59\n")
    windows = json.loads(js)
    assert windows[0]["label"] == "London"
    book = SimpleNamespace(
        enabled=True,
        gate_strict=True,
        session_windows_json=js,
        unlocked_date=None,
        unlocked_note=None,
        risk_base_pct=1.0,
        risk_min_pct=0.25,
        account_starting_balance=10000,
        account_high_water=10000,
        account_current_balance=10000,
        weekly_bias_rules="Up week only",
        daily_bias_rules="Above PDH",
        h4_rules="BOS",
        m15_rules="Retest",
        entry_rules="Wait for displacement",
        exit_rules="TP at next swing",
        invalidation_rules="Close below sweep",
        do_not_trade_rules="No revenge",
        psychology_rules="Stop after 2 losses",
        overview="SMC London",
        strategy_name="Test",
        markets="US30, XAUUSD",
    )
    user = SimpleNamespace(timezone="UTC", id=1, is_authenticated=True)
    gate = session_gate(user, book)
    assert gate["allowed"] is True
    brief = build_multi_tf_brief(book, gate)
    assert brief["completeness"] == 100
    advice = advise_before_trade(book, symbol="US30", thesis="I will revenge and make it back")
    assert advice["verdict"] in ("caution", "no_trade")
    assert advice["warnings"]


def test_owner_can_save_bible(owner_client, app):
    r = owner_client.post(
        "/owner/rules/bible",
        data={
            "strategy_name": "Nathan SMC",
            "overview": "Liquidity sweep then displacement.",
            "markets": "US30, XAUUSD",
            "timeframes": "W, D, H4, M15",
            "weekly_bias_rules": "Trade with weekly candle close.",
            "daily_bias_rules": "Only with daily FVG direction.",
            "h4_rules": "Wait for H4 BOS.",
            "m15_rules": "Enter on M15 retest.",
            "entry_rules": "Confirm displacement + MSS.",
            "exit_rules": "Partial at 1R, runner to next OB.",
            "invalidation_rules": "Close beyond sweep extreme.",
            "do_not_trade_rules": "No mid-range; no revenge.",
            "psychology_rules": "Stop after 2 losses.",
            "session_windows": "London|0,1,2,3,4|07:00|11:30",
            "gate_strict": "on",
            "enabled": "on",
            "risk_base_pct": "1",
            "risk_min_pct": "0.25",
            "account_starting_balance": "10000",
            "account_high_water": "10000",
            "account_current_balance": "10000",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        book = OwnerRulebook.query.filter_by(user_id=1).first()
        # user id may not be 1 — fetch by strategy name
        book = OwnerRulebook.query.filter_by(strategy_name="Nathan SMC").first()
        assert book is not None
        assert "London" in book.session_windows_json
        assert book.gate_strict is True


def test_is_owner_helper(app):
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        trader = User.query.filter_by(username="trader").first()
        assert is_owner_discipline_user(owner) is True
        assert is_owner_discipline_user(trader) is False
