"""End-to-end authenticated workflow (Flask test client)."""

import io
import uuid

import pytest

from app import create_app, db, schema_compat
from app.models.instrument import Instrument
from app.models.trade import Trade
from app.models.trade_replay_event import TradeReplayEvent
from app.models.user import User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
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


def test_signup_profile_trade_replay_analytics_ai_pricing(app, tmp_path):
    app.config["TRADE_SCREENSHOTS_FOLDER"] = str(tmp_path)
    client = app.test_client()
    suffix = uuid.uuid4().hex[:10]
    email = f"journey_{suffix}@e2e.test"
    username = f"jrny{suffix}"[:12]

    r = client.post(
        "/auth/register",
        data={
            "username": username,
            "email": email,
            "password": "Password12345!",
            "confirm_password": "Password12345!",
            "full_name": "Journey User",
            "country_code": "US",
            "phone_number": "+15551234567",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    r = client.get("/dashboard/")
    assert r.status_code == 200

    r = client.post(
        "/auth/profile",
        data={
            "full_name": "Journey User II",
            "bio": "E2E",
            "timezone": "UTC",
            "preferred_currency": "USD",
            "theme": "dark",
            "country_code": "US",
            "phone_number": "+15551234567",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    with app.app_context():
        iid = Instrument.query.filter_by(symbol="EURUSD").first().id

    r = client.post(
        "/trade/add",
        data={
            "symbol": "EURUSD",
            "instrument_id": str(iid),
            "trade_type": "BUY",
            "lot_size": "0.1",
            "entry_price": "1.1",
            "stop_loss": "1.05",
            "take_profit": "1.2",
            "exit_price": "1.11",
            "entry_date": "2024-06-01T10:00:00",
            "exit_date": "2024-06-01T12:00:00",
            "strategy": "Scalping",
            "session_type": "London",
            "timeframe": "15M",
            "emotion": "Confident",
            "pre_trade_plan": "wait for FVG",
            "post_trade_notes": "executed per plan",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    loc = r.headers.get("Location", "")
    assert "/trade/" in loc

    with app.app_context():
        tr = Trade.query.filter_by(symbol="EURUSD").order_by(Trade.id.desc()).first()
        assert tr is not None
        tid = tr.id
        uid = tr.user_id

    r = client.post(
        f"/trade/{tid}/edit",
        data={
            "symbol": "EURUSD",
            "instrument_id": str(iid),
            "trade_type": "BUY",
            "lot_size": "0.2",
            "entry_price": "1.1",
            "stop_loss": "1.05",
            "take_profit": "1.2",
            "exit_price": "1.12",
            "entry_date": "2024-06-01T10:00:00",
            "exit_date": "2024-06-01T13:00:00",
            "strategy": "Scalping",
            "session_type": "London",
            "timeframe": "15M",
            "emotion": "Disciplined",
            "pre_trade_plan": "updated",
            "post_trade_notes": "edited notes",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
        b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    buf = io.BytesIO(png)
    r = client.post(
        f"/replay/trade/{tid}/add",
        data={"event_type": "before", "note": "chart", "media": (buf, "s.png")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    if r.status_code == 404:
        pytest.skip("replay blueprint not registered")
    assert r.status_code in (302, 303)

    with app.app_context():
        assert TradeReplayEvent.query.filter_by(trade_id=tid).count() >= 1

    for path in (
        "/dashboard/analytics",
        "/dashboard/emotions",
        "/dashboard/ai",
    ):
        r = client.get(path)
        assert r.status_code == 200, path

    r = client.get("/pricing")
    assert r.status_code in (200, 302)

    r = client.get(f"/api/db/instruments/by-id/{iid}")
    assert r.status_code == 200
    js = r.get_json()
    assert js.get("success") and js.get("symbol") == "EURUSD"
    assert js.get("frontend_category") == "forex"
