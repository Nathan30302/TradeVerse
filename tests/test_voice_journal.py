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
        db.session.add(
            Instrument(
                symbol="US30",
                name="Dow Jones",
                instrument_type="index",
                category="Indices",
                pip_size=1.0,
                contract_size=1,
                tick_value=1.0,
                is_active=True,
            )
        )
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


def test_parse_yes_no_status_and_bare_number():
    assert parse_voice_text("yes that's right")["yes_no"] == "yes"
    assert parse_voice_text("already done")["status"] == "closed"
    assert parse_voice_text("still in it")["status"] == "open"
    assert parse_voice_text("1.17240")["bare_number"] == 1.1724
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
    assert "Voice Journal" in body
    assert "Just talk" in body


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


def test_parse_at_price_as_entry():
    out = parse_voice_text("I went long on US30 at 42500 stop 42350")
    assert out["symbol"] == "US30"
    assert out["trade_type"] == "BUY"
    assert out["entry_price"] == 42500
    assert out["stop_loss"] == 42350


def test_conversation_skips_fields_already_said():
    from app.services.voice_conversation import fallback_turn

    first = fallback_turn("I went long on US30 at 42500 stop 42350")
    d = first["draft"]
    assert d["symbol"] == "US30"
    assert d["trade_type"] == "BUY"
    assert d["entry_price"] == 42500
    assert d["stop_loss"] == 42350
    assert first["complete"] is False
    reply = (first["reply"] or "").lower()
    assert "got it" in reply
    assert "long" not in reply or "still" in reply or "done" in reply or "target" in reply or "chart" in reply
    assert "what did you trade" not in reply

    second = fallback_turn("still in it, breakout off the open", d)
    assert second["draft"]["status"] == "open"
    assert "Breakout" in (second["draft"].get("setup_tags") or [])
    assert "long or short" not in (second["reply"] or "").lower()
    assert "session" in (second["reply"] or "").lower()

    third = fallback_turn("London this morning", second["draft"])
    assert third["draft"]["session_type"]
    assert third["draft"]["entry_time"]
    assert "what did you trade" not in (third["reply"] or "").lower()
    assert third["ask_screenshot"] is True
    assert third["screenshot_kind"] == "before"


def test_voice_turn_api_extracts_and_asks_once(logged_client):
    r = logged_client.post(
        "/trade/api/voice-turn",
        json={"transcript": "I went long on US30 at 42500 stop 42350"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["draft"]["trade_type"] == "BUY"
    assert data["draft"]["entry_price"] == 42500
    assert data["draft"]["symbol"] == "US30"
    assert data["complete"] is False
    assert data["reply"]
    assert "field" not in data["reply"].lower()
    assert "step" not in data["reply"].lower()


def test_conversation_completes_after_screenshot_skip():
    from app.services.voice_conversation import fallback_turn, required_ready

    d = fallback_turn(
        "Bought gold at 3650 stop 3640, still in it this morning london because it swept the low"
    )["draft"]
    assert d["symbol"] == "XAUUSD"
    assert d["session_type"]
    assert d["entry_time"]
    assert required_ready(d)
    shot = fallback_turn("yeah that's it", d, has_screenshot=False)
    assert shot["ask_screenshot"] is True
    assert shot["screenshot_kind"] == "before"
    after = fallback_turn("I uploaded the before chart.", shot["draft"], has_before=True)
    assert after["ask_screenshot"] is True
    assert after["screenshot_kind"] == "after"
    done = fallback_turn("no", after["draft"], has_before=True, skip_screenshot=True)
    assert done["complete"] is True
    assert done["ask_screenshot"] is False


def test_does_not_infer_session_from_clock():
    from app.services.voice_conversation import fallback_turn

    first = fallback_turn(
        "I went long on US30 at 42500 stop 42350 still in it",
        session_hint={"session_type": "New York Session", "chip": "NY"},
    )
    assert not first["draft"].get("session_type")
    assert "session" in (first["reply"] or "").lower()


def test_thesis_and_dump_keep_user_words():
    from app.services.voice_conversation import draft_to_form_fields, fallback_turn, guard_reply

    text = "I went long on US30 at 42500 stop 42350 because it swept the London open"
    first = fallback_turn(text)
    notes = first["draft"].get("thesis_notes") or ""
    dump = first["draft"].get("voice_dump") or ""
    assert "swept the London open" in notes
    assert "swept the London open" in dump
    assert "what did you trade" not in (first["reply"] or "").lower()
    assert "long or short" not in (first["reply"] or "").lower()

    fields = draft_to_form_fields(first["draft"])
    assert "swept the London open" in fields["guide_voice_dump"]
    assert "swept the London open" in fields["guide_why"]

    rewritten = dict(first["draft"])
    rewritten["thesis_notes"] = "Entered a Dow long after a liquidity raid on the cash open."
    guarded = fallback_turn("still in it", rewritten)
    kept = (guarded["draft"].get("thesis_notes") or "") + " " + (guarded["draft"].get("voice_dump") or "")
    assert "swept the London open" in kept
    assert "liquidity raid on the cash open" not in (guarded["draft"].get("thesis_notes") or "")
    assert "long or short" not in (guarded["reply"] or "").lower()
    assert "what did you trade" not in (guarded["reply"] or "").lower()

    filled = first["draft"]
    assert "entry" not in guard_reply("What was your entry?", filled).lower() or filled.get("entry_price") is None


def test_voice_turn_keeps_verbatim_dump(logged_client):
    r = logged_client.post(
        "/trade/api/voice-turn",
        json={
            "transcript": "I went long on US30 at 42500 stop 42350 because it swept the London open",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    dump = (data.get("form") or {}).get("guide_voice_dump") or ""
    why = (data.get("form") or {}).get("guide_why") or ""
    assert "swept the London open" in dump
    assert "swept the London open" in why
    assert "what did you trade" not in (data.get("reply") or "").lower()

