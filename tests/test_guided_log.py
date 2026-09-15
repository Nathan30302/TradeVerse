"""Voice Journal / guided log: one-question interview that saves through Add Trade."""

import pytest

from app import create_app, db, schema_compat
from app.models.instrument import Instrument
from app.models.trade import Trade
from app.models.user import User
from app.routes.trade import _compose_guided_log_fields


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        u = User(username="guser", email="guser@example.com")
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
        data={"username": "guser", "password": "password12"},
        follow_redirects=True,
    )
    return c


def test_guide_page_loads(logged_client):
    r = logged_client.get("/trade/guide")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Voice Journal" in body
    assert "Just talk" in body
    assert "tv-vj-orb" in body
    assert "tv-vj-canvas" in body
    assert "tv-vj-water" in body
    assert "tv-vj-shot-before" in body
    assert "tv-vj-shot-after" in body
    assert "tv-vj-chips" in body


def test_compose_guided_fields():
    class F(dict):
        def getlist(self, key):
            return self._lists.get(key, [])

        def __init__(self):
            super().__init__(from_guide="1", guide_feeling_before="Calm & Focused", guide_why="Swept the low then BOS.")
            self._lists = {"guide_confirm": ["premarket", "confirmed"]}

    out = _compose_guided_log_fields(F())
    assert out
    assert "Swept the low" in out["pre_trade_plan"]
    assert "Calm & Focused" in out["pre_trade_plan"]
    assert out["checklist_completed"] is True
    assert out["emotion"] == "Calm & Focused"


def test_guided_post_creates_open_trade(logged_client, app):
    with app.app_context():
        inst = Instrument.query.filter_by(symbol="EURUSD").first()
        iid = inst.id
    r = logged_client.post(
        "/trade/add",
        data={
            "from_guide": "1",
            "symbol": "EURUSD",
            "instrument_id": str(iid),
            "trade_type": "BUY",
            "lot_size": "0.1",
            "entry_price": "1.10000",
            "stop_loss": "1.09500",
            "trade_log_status": "open",
            "guide_feeling_before": "Disciplined",
            "guide_why": "Session open retest of support.",
            "guide_followed_plan": "yes",
            "guide_confirm": ["playbook"],
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        t = Trade.query.filter_by(symbol="EURUSD").order_by(Trade.id.desc()).first()
        assert t is not None
        assert t.status == "OPEN"
        assert t.trade_type == "BUY"
        assert "Session open retest" in (t.pre_trade_plan or "")
        assert t.emotion == "Disciplined"
        assert t.playbook_followed is True


def test_guided_closed_needs_strategy_or_composes_notes(logged_client, app):
    with app.app_context():
        inst = Instrument.query.filter_by(symbol="EURUSD").first()
        iid = inst.id
    r = logged_client.post(
        "/trade/add",
        data={
            "from_guide": "1",
            "symbol": "EURUSD",
            "instrument_id": str(iid),
            "trade_type": "SELL",
            "lot_size": "1",
            "entry_price": "1.10000",
            "exit_price": "1.09000",
            "trade_log_status": "closed",
            "strategy": "Price Action",
            "guide_feeling_before": "Nervous",
            "guide_why": "Broke below range after news fade.",
            "guide_feeling_after": "Calm & Focused",
            "guide_what_happened": "Ran to target, no extra size.",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        t = Trade.query.filter_by(status="CLOSED").order_by(Trade.id.desc()).first()
        assert t is not None
        assert t.strategy == "Price Action"
        assert "Broke below range" in (t.pre_trade_plan or "")
        assert "Ran to target" in (t.post_trade_notes or "")
        assert t.emotion == "Calm & Focused"


def test_voice_closed_saves_without_strategy(logged_client, app):
    with app.app_context():
        inst = Instrument.query.filter_by(symbol="EURUSD").first()
        iid = inst.id
    r = logged_client.post(
        "/trade/add",
        data={
            "from_guide": "1",
            "symbol": "EURUSD",
            "instrument_id": str(iid),
            "trade_type": "BUY",
            "lot_size": "0.1",
            "entry_price": "1.17240",
            "exit_price": "1.17440",
            "trade_log_status": "closed",
            "guide_why": "London sweep then BOS.",
            "guide_emotions": "Confident, Nervous",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        t = Trade.query.filter_by(status="CLOSED").order_by(Trade.id.desc()).first()
        assert t is not None
        assert t.strategy == "Other"
        assert "London sweep" in (t.pre_trade_plan or "")
        assert t.emotion == "Confident"
