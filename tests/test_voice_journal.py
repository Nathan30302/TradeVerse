"""Voice Journal parse / extract APIs and dashboard status."""

from io import BytesIO

import pytest

from app import create_app, db, schema_compat
from app.models.instrument import Instrument
from app.models.trade import Trade
from app.models.user import User
from app.services.voice_journal import parse_voice_text, preview_metrics, compose_guided_fields


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        u = User(username="vjuser", email="vj@example.com")
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
        gold = Instrument(
            symbol="XAUUSD",
            name="Gold",
            instrument_type="metal",
            category="Energies",
            pip_size=0.1,
            contract_size=100,
            tick_value=1.0,
            is_active=True,
        )
        db.session.add(gold)
        db.session.commit()
        yield app


@pytest.fixture
def logged_client(app):
    c = app.test_client()
    c.post(
        "/auth/login",
        data={"username": "vjuser", "password": "password12"},
        follow_redirects=True,
    )
    return c


def test_parse_voice_gold_buy_levels():
    out = parse_voice_text(
        "I bought gold during London after the liquidity sweep. Entry 3650.20 stop 3640.20 take profit 3670.20"
    )
    assert out["symbol"] == "XAUUSD"
    assert out["trade_type"] == "BUY"
    assert out["entry_price"] == 3650.20
    assert out["stop_loss"] == 3640.20
    assert out["take_profit"] == 3670.20
    assert out["session_type"] == "London Session"
    assert "Liquidity sweep" in out["setup_tags"]


def test_parse_voice_does_not_guess_side_from_empty():
    out = parse_voice_text("")
    assert out["symbol"] is None
    assert out["trade_type"] is None


def test_preview_rr():
    m = preview_metrics(
        entry=1.17240,
        stop_loss=1.17140,
        take_profit=1.17440,
        exit_price=None,
        side="BUY",
        lot_size=1,
        symbol="EURUSD",
    )
    assert m["rr"] == 2.0
    assert m["rr_label"] == "1:2"


def test_compose_emotions_and_setup():
    class F(dict):
        def getlist(self, key):
            return []

        def __init__(self):
            super().__init__(
                from_guide="1",
                guide_emotions="Confident, Nervous",
                guide_setup_tags="Liquidity sweep",
                guide_why="Swept the previous low then BOS.",
                guide_session="London Session",
                session_type="London Session",
                guide_followed_plan="yes",
            )

    out = compose_guided_fields(F())
    assert out["emotion"] == "Confident"
    assert out["strategy"] == "Smart Money Concepts (SMC)"
    assert "Liquidity sweep" in (out["tags"] or "")
    assert out["session_type"] == "London Session"
    assert out["playbook_followed"] is True


def test_voice_alias_and_quick_mode(logged_client):
    r = logged_client.get("/trade/voice?mode=quick")
    assert r.status_code in (302, 303)
    follow = logged_client.get("/trade/guide?mode=quick")
    assert follow.status_code == 200
    body = follow.get_data(as_text=True)
    assert "Have 30 seconds" in body
    assert "Voice Journal" in body


def test_add_trade_keeps_manual_form(logged_client):
    r = logged_client.get("/trade/add")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Log trade" in body
    assert "Voice Journal" in body
    assert "instrument-search" in body


def test_parse_voice_api_resolves_instrument(logged_client):
    r = logged_client.post(
        "/trade/api/parse-voice",
        json={"text": "EURUSD buy entry 1.17240 stop 1.17140 tp 1.17440"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["parsed"]["symbol"] == "EURUSD"
    assert data["parsed"]["trade_type"] == "BUY"
    assert data["instrument"]["symbol"] == "EURUSD"
    assert data["metrics"]["rr"] == 2.0


def test_extract_chart_requires_image(logged_client):
    r = logged_client.post("/trade/api/extract-chart")
    assert r.status_code == 400
    data = r.get_json()
    assert data["ok"] is False


def test_extract_chart_rejects_empty_file(logged_client):
    r = logged_client.post(
        "/trade/api/extract-chart",
        data={"image": (BytesIO(b""), "chart.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is False


def test_journal_status_api(logged_client, app):
    r = logged_client.get("/trade/api/journal-status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["today_total"] == 0
    with app.app_context():
        u = User.query.filter_by(username="vjuser").first()
        inst = Instrument.query.filter_by(symbol="EURUSD").first()
        t = Trade(
            user_id=u.id,
            instrument_id=inst.id,
            symbol="EURUSD",
            trade_type="BUY",
            lot_size=0.1,
            entry_price=1.1,
            status="CLOSED",
            exit_price=1.11,
        )
        db.session.add(t)
        db.session.commit()
    r2 = logged_client.get("/trade/api/journal-status")
    data2 = r2.get_json()
    assert data2["pending_count"] >= 1


def test_dashboard_has_voice_and_journal_trade(logged_client):
    r = logged_client.get("/dashboard/")
    if r.status_code != 200:
        r = logged_client.get("/dashboard")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Voice" in body
    assert "Journal Trade" in body or "Add Trade" in body
