"""Daily risk lock, MAE/MFE, mistake chips, and import review."""

from app import create_app, db, schema_compat
from app.models.broker import ImportedTradeSource
from app.models.instrument import Instrument
from app.models.trade import Trade
from app.models.user import User
from app.utils.timeutil import utc_now
from app.services.analytics_engine import leftover_r, leftover_strip_stats
from app.services.daily_risk import get_daily_risk_snapshot
from app.services.mistake_tags import serialize_mistake_tags

import pytest


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        u = User(username="juser", email="juser@example.com")
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
        data={"username": "juser", "password": "password12"},
        follow_redirects=True,
    )
    return c


def _user_and_instrument(app):
    u = User.query.filter_by(username="juser").first()
    inst = Instrument.query.filter_by(symbol="EURUSD").first()
    return u, inst


def test_settings_save_daily_risk_limits(logged_client, app):
    r = logged_client.post(
        "/auth/profile",
        data={
            "full_name": "J",
            "bio": "",
            "timezone": "UTC",
            "preferred_currency": "USD",
            "theme": "dark",
            "after_save": "settings",
            "daily_loss_limit_r": "2",
            "daily_max_trades": "3",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        u = User.query.filter_by(username="juser").first()
        assert u.daily_loss_limit_r == 2.0
        assert u.daily_max_trades == 3


def test_daily_max_trades_blocks_add(logged_client, app):
    logged_client.post(
        "/auth/profile",
        data={
            "full_name": "J",
            "bio": "",
            "timezone": "UTC",
            "preferred_currency": "USD",
            "theme": "dark",
            "after_save": "settings",
            "daily_loss_limit_r": "",
            "daily_max_trades": "1",
        },
        follow_redirects=False,
    )
    with app.app_context():
        u, inst = _user_and_instrument(app)
        assert u.daily_max_trades == 1
        t = Trade(
            user_id=u.id,
            symbol="EURUSD",
            instrument_id=inst.id,
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=utc_now(),
            status="OPEN",
        )
        db.session.add(t)
        db.session.commit()
        snap = get_daily_risk_snapshot(u)
        assert snap["locked"] is True
        iid = inst.id

    r = logged_client.post(
        "/trade/add",
        data={
            "symbol": "EURUSD",
            "instrument_id": str(iid),
            "trade_type": "BUY",
            "lot_size": "1",
            "entry_price": "1.1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True).lower()
    assert "daily risk" in body or "trade count" in body or "trade limit" in body


def test_daily_loss_lock_from_closed_r(app):
    with app.app_context():
        u, inst = _user_and_instrument(app)
        u.daily_loss_limit_r = 1.0
        t = Trade(
            user_id=u.id,
            symbol="EURUSD",
            instrument_id=inst.id,
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.10,
            stop_loss=1.09,
            exit_price=1.08,
            entry_date=utc_now(),
            exit_date=utc_now(),
            status="CLOSED",
            profit_loss=-20.0,
            risk_amount=10.0,
        )
        db.session.add(t)
        db.session.commit()
        snap = get_daily_risk_snapshot(u)
        assert snap["locked"] is True
        assert snap["used_r"] <= -1.0


def test_close_saves_mae_mfe(logged_client, app):
    with app.app_context():
        u, inst = _user_and_instrument(app)
        t = Trade(
            user_id=u.id,
            symbol="EURUSD",
            instrument_id=inst.id,
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.10000,
            stop_loss=1.09000,
            entry_date=utc_now(),
            status="OPEN",
        )
        db.session.add(t)
        db.session.commit()
        tid = t.id

    r = logged_client.post(
        f"/trade/{tid}/close",
        data={
            "exit_price": "1.10500",
            "mae_price": "1.09500",
            "mfe_price": "1.10800",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        t2 = db.session.get(Trade, tid)
        assert t2.status == "CLOSED"
        assert t2.mae_price == pytest.approx(1.09500)
        assert t2.mfe_price == pytest.approx(1.10800)
        assert leftover_r(t2) is not None
        assert leftover_r(t2) > 0


def test_mistake_chips_save_and_filter(logged_client, app):
    with app.app_context():
        u, inst = _user_and_instrument(app)
        t = Trade(
            user_id=u.id,
            symbol="EURUSD",
            instrument_id=inst.id,
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=utc_now(),
            status="CLOSED",
            exit_price=1.09,
            exit_date=utc_now(),
            profit_loss=-1.0,
            mistake_tags=serialize_mistake_tags(["early_exit"]),
        )
        other = Trade(
            user_id=u.id,
            symbol="EURUSD",
            instrument_id=inst.id,
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=utc_now(),
            status="CLOSED",
            exit_price=1.11,
            exit_date=utc_now(),
            profit_loss=1.0,
        )
        db.session.add_all([t, other])
        db.session.commit()
        keep_id = t.id

    r = logged_client.get("/trade/list?mistake=early_exit")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Early exit" in body
    assert f"/trade/{keep_id}" in body


def test_leftover_strip_stats():
    class T:
        trade_type = "BUY"
        entry_price = 1.10
        stop_loss = 1.09
        lot_size = 1.0
        risk_amount = None
        exit_price = 1.105
        mfe_price = 1.12

    stats = leftover_strip_stats([T()])
    assert stats is not None
    assert stats["count"] == 1
    assert stats["sum_r"] > 0


def test_import_review_page(logged_client, app):
    with app.app_context():
        u, inst = _user_and_instrument(app)
        src = ImportedTradeSource(
            user_id=u.id,
            source_type="file",
            broker_id="generic",
            filename="stmt.csv",
            trades_imported=1,
            status="completed",
        )
        db.session.add(src)
        db.session.flush()
        t = Trade(
            user_id=u.id,
            symbol="EURUSD",
            instrument_id=inst.id,
            trade_type="BUY",
            lot_size=1.0,
            entry_price=1.1,
            entry_date=utc_now(),
            status="CLOSED",
            exit_price=1.11,
            imported_source_id=src.id,
        )
        db.session.add(t)
        db.session.commit()
        sid = src.id
        tid = t.id

    r = logged_client.get(f"/imports/review/{sid}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Review imported" in body
    assert "EURUSD" in body

    skip = logged_client.post(
        f"/imports/review/{sid}",
        data={"trade_id": str(tid), "action": "skip"},
        follow_redirects=True,
    )
    assert skip.status_code == 200
    with app.app_context():
        t2 = db.session.get(Trade, tid)
        assert t2.status == "CANCELLED"
