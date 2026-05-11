"""Add Trade server-side validation (instrument required, id/symbol match)."""

import pytest

from app import create_app, db, schema_compat
from app.models.instrument import Instrument
from app.models.user import User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        u = User(username="tlog", email="tlog@example.com")
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
        data={"username": "tlog", "password": "password12"},
        follow_redirects=True,
    )
    return c


def test_add_trade_rejects_missing_instrument(logged_client):
    r = logged_client.post(
        "/trade/add",
        data={
            "symbol": "",
            "instrument_id": "",
            "trade_type": "BUY",
            "lot_size": "1",
            "entry_price": "1.1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True).lower()
    assert "instrument" in body


def test_add_trade_rejects_symbol_id_mismatch(logged_client, app):
    with app.app_context():
        iid = Instrument.query.filter_by(symbol="EURUSD").first().id
    r = logged_client.post(
        "/trade/add",
        data={
            "symbol": "XAUUSD",
            "instrument_id": str(iid),
            "trade_type": "BUY",
            "lot_size": "1",
            "entry_price": "1.1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True).lower()
    assert "re-select" in body or "invalid" in body
