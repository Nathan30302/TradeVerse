"""Cooldown triggers after trade add, edit, and close (emotion + loss streak)."""

from datetime import timedelta

import pytest

from app import create_app, db, schema_compat
from app.utils.timeutil import utc_now
from app.models.cooldown import Cooldown
from app.models.instrument import Instrument
from app.models.trade import Trade
from app.models.user import User
from app.models.cooldown import normalize_emotion_for_cooldown, should_trigger_cooldown
from app.routes.trade import _apply_post_trade_cooldowns


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        u = User(username="cduser", email="cduser@example.com")
        u.set_password("password12")
        db.session.add(u)
        inst = Instrument(
            symbol="EURUSD",
            name="EUR/USD",
            instrument_type="forex",
            category="Forex",
            pip_size=0.0001,
            contract_size=100000,
            tick_value=10.0,
            is_active=True,
        )
        db.session.add(inst)
        db.session.commit()
        yield app


@pytest.fixture
def logged_client(app):
    c = app.test_client()
    c.post(
        "/auth/login",
        data={"username": "cduser", "password": "password12"},
        follow_redirects=True,
    )
    return c


def _clear_cooldowns(app):
    with app.app_context():
        Cooldown.query.delete()
        db.session.commit()


def test_emotion_alias_revenge_maps_to_rules(app):
    with app.app_context():
        assert normalize_emotion_for_cooldown('Revenge') == 'Revenge Trading'
        assert should_trigger_cooldown('Revenge')


def test_apply_post_trade_cooldowns_dangerous_emotion(app):
    _clear_cooldowns(app)
    with app.app_context():
        u = User.query.filter_by(username="cduser").first()
        t = Trade(
            user_id=u.id,
            symbol="EURUSD",
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=utc_now(),
            status="CLOSED",
            exit_price=1.09,
            exit_date=utc_now(),
            profit_loss=-5.0,
            strategy="Other",
        )
        db.session.add(t)
        db.session.commit()

        note = _apply_post_trade_cooldowns(u.id, "Angry", t)
        assert note is not None
        cd = Cooldown.query.filter_by(user_id=u.id, is_active=True).first()
        assert cd is not None
        assert cd.trigger_emotion == "Angry"


def test_apply_post_trade_cooldowns_exempt_emotion_no_cooldown(app):
    _clear_cooldowns(app)
    with app.app_context():
        u = User.query.filter_by(username="cduser").first()
        t = Trade(
            user_id=u.id,
            symbol="EURUSD",
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=utc_now(),
            status="CLOSED",
            exit_price=1.12,
            exit_date=utc_now(),
            profit_loss=10.0,
            strategy="Other",
        )
        db.session.add(t)
        db.session.commit()

        _apply_post_trade_cooldowns(u.id, "Disciplined", t)
        assert Cooldown.query.filter_by(user_id=u.id, is_active=True).first() is None


def test_apply_post_trade_cooldowns_loss_streak(app):
    _clear_cooldowns(app)
    with app.app_context():
        u = User.query.filter_by(username="cduser").first()
        now = utc_now()
        for i in range(2):
            tr = Trade(
                user_id=u.id,
                symbol="EURUSD",
                trade_type="BUY",
                lot_size=1.0,
                entry_price=1.1,
                entry_date=now - timedelta(days=1, hours=i),
                status="CLOSED",
                exit_price=1.09,
                exit_date=now - timedelta(hours=3 - i),
                profit_loss=-1.0,
                strategy="Other",
            )
            db.session.add(tr)
        db.session.commit()

        t3 = Trade(
            user_id=u.id,
            symbol="EURUSD",
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=now,
            status="CLOSED",
            exit_price=1.08,
            exit_date=now,
            profit_loss=-2.0,
            strategy="Other",
        )
        db.session.add(t3)
        db.session.commit()

        note = _apply_post_trade_cooldowns(u.id, None, t3)
        assert note is not None
        cd = Cooldown.query.filter_by(user_id=u.id, is_active=True).first()
        assert cd is not None
        assert "Loss" in cd.trigger_emotion


def test_edit_trade_POST_sets_emotion_cooldown(logged_client, app):
    _clear_cooldowns(app)
    with app.app_context():
        u = User.query.filter_by(username="cduser").first()
        inst = Instrument.query.filter_by(symbol="EURUSD").first()
        iid = inst.id
        uid = u.id
        t = Trade(
            user_id=u.id,
            instrument_id=inst.id,
            symbol="EURUSD",
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=utc_now(),
            status="CLOSED",
            exit_price=1.09,
            exit_date=utc_now(),
            profit_loss=-3.0,
            strategy="Other",
            emotion="Calm & Focused",
        )
        db.session.add(t)
        db.session.commit()
        tid = t.id

    r = logged_client.post(
        f"/trade/{tid}/edit",
        data={
            "symbol": "EURUSD",
            "instrument_id": str(iid),
            "trade_type": "BUY",
            "lot_size": "1",
            "entry_price": "1.1",
            "exit_price": "1.09",
            "stop_loss": "",
            "take_profit": "",
            "strategy": "Other",
            "session_type": "",
            "timeframe": "",
            "emotion": "Greedy",
            "confidence_level": "",
            "pre_trade_plan": "planned enough",
            "post_trade_notes": "review notes",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        cd = Cooldown.query.filter_by(user_id=uid, is_active=True).first()
        assert cd is not None
        assert cd.trigger_emotion == "Greedy"


def test_quick_review_preserves_symbol_and_triggers_cooldown(logged_client, app):
    """Trade view quick review must not POST empty symbol (would wipe the trade)."""
    _clear_cooldowns(app)
    with app.app_context():
        u = User.query.filter_by(username="cduser").first()
        inst = Instrument.query.filter_by(symbol="EURUSD").first()
        t = Trade(
            user_id=u.id,
            instrument_id=inst.id,
            symbol="EURUSD",
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=utc_now(),
            status="CLOSED",
            exit_price=1.09,
            exit_date=utc_now(),
            profit_loss=-1.0,
            strategy="Other",
            emotion="Disciplined",
        )
        db.session.add(t)
        db.session.commit()
        tid = t.id

    r = logged_client.post(
        f"/trade/{tid}/edit",
        data={
            "tv_quick_review": "1",
            "emotion": "Angry",
            "discipline_score": "9",
            "lessons_learned": "Stopped early next time",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        t2 = Trade.query.filter_by(id=tid).first()
        assert t2.symbol == "EURUSD"
        assert t2.emotion == "Angry"
        cd = Cooldown.query.filter_by(user_id=t2.user_id, is_active=True).first()
        assert cd is not None
        assert cd.trigger_emotion == "Angry"
