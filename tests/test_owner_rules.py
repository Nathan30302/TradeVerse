"""Owner Rules Desk — multi-strategy discipline coach (owner-only)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import create_app, db, schema_compat
from app.models.owner_rules import OwnerRulebook, OwnerStrategy
from app.models.user import User
from app.services.owner_discipline import (
    advise_before_trade,
    build_multi_tf_brief,
    calc_lot_size,
    calc_ten_two_two,
    drawdown_fraction,
    get_or_create_rulebook,
    is_owner_discipline_user,
    list_strategies,
    record_day_trade_result,
    session_gate,
    suggested_risk,
    windows_from_form,
)
from app.services.owner_strategy_seeds import FX_ALEXG_SLUG, VINCENT_BR_SLUG


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
    r = c.get("/owner/rules/")
    assert r.status_code == 200
    assert b"Break &amp; Retest" in r.data or b"Break & Retest" in r.data
    c.get("/auth/logout", follow_redirects=True)
    c.post("/auth/login", data={"username": "trader", "password": "password12"}, follow_redirects=True)
    with c.session_transaction() as sess:
        uid = sess.get("_user_id")
    with app.app_context():
        u = User.query.get(int(uid))
        assert u.username == "trader"
        assert (u.role or "").lower() == "user"
    assert c.get("/owner/rules/").status_code == 404


def test_fx_alexg_seeded_on_desk_open(app):
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        book = get_or_create_rulebook(owner)
        strategies = list_strategies(owner)
        assert len(strategies) >= 2
        assert strategies[0].slug == FX_ALEXG_SLUG
        assert strategies[1].slug == VINCENT_BR_SLUG
        assert book.active_strategy_id == strategies[0].id
        assert strategies[0].max_trades_per_day == 2
        assert strategies[0].stop_after_first_win is True
        checklist = json.loads(strategies[0].checklist_json or "{}")
        assert len(checklist.get("pre_trade") or []) >= 8
        assert len(checklist.get("states") or []) == 6
        v_check = json.loads(strategies[1].checklist_json or "{}")
        assert len(v_check.get("hurdles") or []) == 5
        assert strategies[1].max_trades_per_day == 3


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


def test_lot_size_formula():
    # 10000 * 1% / (20 * 10) = 100 / 200 = 0.5
    result = calc_lot_size(balance=10000, risk_pct=1.0, sl_pips=20, pip_value=10)
    assert result["error"] is None
    assert result["lots"] == 0.5
    assert result["risk_cash"] == 100.0


def test_ten_two_two_formula():
    result = calc_ten_two_two(balance=10000, allocation_pct=10, option_loss_pct=20)
    assert result["ok"] is True
    assert result["account_risk_pct"] == 2.0
    assert result["position_dollars"] == 1000.0
    over = calc_ten_two_two(balance=10000, allocation_pct=15, option_loss_pct=20)
    assert over["ok"] is False


def test_activate_vincent_strategy(app, owner_client):
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        get_or_create_rulebook(owner)
        vincent = OwnerStrategy.query.filter_by(user_id=owner.id, slug=VINCENT_BR_SLUG).first()
        assert vincent is not None
        sid = vincent.id
    r = owner_client.post(
        "/owner/rules/activate",
        data={"strategy_id": str(sid)},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Vincent Desiano" in r.data
    assert b"10-2-2" in r.data
    r2 = owner_client.post(
        "/owner/rules/ten-two-two",
        data={"balance": "10000", "allocation_pct": "10", "option_loss_pct": "20"},
        follow_redirects=True,
    )
    assert r2.status_code == 200
    assert b"2.00% account" in r2.data or b"2% account" in r2.data


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
        trades_today=0,
        wins_today=0,
        losses_today=0,
        day_locked=False,
        day_lock_reason=None,
        day_key=None,
        max_trades_per_day=2,
    )
    user = SimpleNamespace(timezone="UTC", id=1, is_authenticated=True)
    gate = session_gate(user, book)
    assert gate["allowed"] is True
    brief = build_multi_tf_brief(book, gate)
    assert brief["completeness"] == 100
    advice = advise_before_trade(book, symbol="US30", thesis="I will revenge and make it back")
    assert advice["verdict"] in ("caution", "no_trade")
    assert advice["warnings"]


def test_daily_stop_after_first_win(app):
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        get_or_create_rulebook(owner)
        status = record_day_trade_result(owner, "win")
        assert status["wins_today"] == 1
        assert status["locked"] is True
        assert "done for the day" in (status["reason"] or "").lower()


def test_daily_second_chance_after_loss(app):
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        get_or_create_rulebook(owner)
        status = record_day_trade_result(owner, "loss")
        assert status["losses_today"] == 1
        assert status["locked"] is False
        assert status["remaining"] == 1
        status = record_day_trade_result(owner, "loss")
        assert status["trades_today"] == 2
        assert status["locked"] is True


def test_owner_can_save_desk_settings(owner_client, app):
    r = owner_client.post(
        "/owner/rules/bible",
        data={
            "action": "desk",
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
        owner = User.query.filter_by(username="nathan").first()
        book = OwnerRulebook.query.filter_by(user_id=owner.id).first()
        assert book is not None
        assert book.account_current_balance == 10000
        assert book.gate_strict is True
        strat = OwnerStrategy.query.filter_by(user_id=owner.id, slug=FX_ALEXG_SLUG).first()
        assert strat is not None


def test_lot_calc_route(owner_client):
    r = owner_client.post(
        "/owner/rules/lot-size",
        data={
            "balance": "10000",
            "risk_pct": "1",
            "sl_pips": "20",
            "pip_value": "10",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"0.5 lots" in r.data


def test_is_owner_helper(app):
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        trader = User.query.filter_by(username="trader").first()
        assert is_owner_discipline_user(owner) is True
        assert is_owner_discipline_user(trader) is False


def test_advise_rejects_off_watchlist(app):
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        book = get_or_create_rulebook(owner)
        from app.services.owner_discipline import get_active_strategy

        strategy = get_active_strategy(owner, book)
        advice = advise_before_trade(
            book,
            symbol="DOGEUSDT",
            thesis="Weekly and daily bullish, AOI retest with engulfing",
            strategy=strategy,
        )
        assert any("approved" in w.lower() or "instrument" in w.lower() for w in advice["warnings"])


def test_practice_and_ritual_seeded(app):
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        book = get_or_create_rulebook(owner)
        from app.services.owner_discipline import get_active_strategy, build_desk_brief
        from app.services.owner_setup_coach import practice_plan_for, ritual_for

        strategy = get_active_strategy(owner, book)
        practice = practice_plan_for(strategy)
        ritual = ritual_for(strategy)
        assert practice.get("duration_minutes") == 120
        assert len(practice.get("blocks") or []) >= 4
        assert len(ritual) >= 5
        brief = build_desk_brief(owner)
        assert brief["practice"]["title"]
        assert len(brief["ritual"]) >= 5


def test_setup_coach_without_key_is_graceful(app, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with app.app_context():
        owner = User.query.filter_by(username="nathan").first()
        book = get_or_create_rulebook(owner)
        from app.services.owner_discipline import get_active_strategy
        from app.services.owner_setup_coach import analyze_setup_screenshots

        strategy = get_active_strategy(owner, book)
        result = analyze_setup_screenshots(strategy=strategy, images=[], notes="test")
        assert result["ok"] is False
        assert result["verdict"] in ("wait", "no_trade")


def test_desk_shows_practice_tab(owner_client):
    r = owner_client.get("/owner/rules/")
    assert r.status_code == 200
    assert b"Practice today" in r.data
    assert b"Screenshot coach" in r.data
    assert b"Before I enter" in r.data
    assert b"Daily 2-hour" in r.data
