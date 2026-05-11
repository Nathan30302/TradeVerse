"""Replay media uploads: multipart, size, linkage."""

import io
import os
from datetime import datetime

import pytest

from app import create_app, db, schema_compat
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
        u = User(username="rep", email="rep@test.dev")
        u.set_password("password12345")
        db.session.add(u)
        db.session.commit()
        t = Trade(
            user_id=u.id,
            symbol="EURUSD",
            trade_type="BUY",
            lot_size=0.1,
            entry_price=1.1,
            status="OPEN",
        )
        db.session.add(t)
        db.session.commit()
        yield app, u.id, t.id


def test_replay_note_and_png_upload(app, tmp_path):
    app_obj, uid, tid = app
    app_obj.config["TRADE_SCREENSHOTS_FOLDER"] = str(tmp_path)

    data = {
        "event_type": "note",
        "note": "scale-in",
    }
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
        b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    buf = io.BytesIO(png)
    buf.name = "chart.png"

    client = app_obj.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)

    resp = client.post(
        f"/replay/trade/{tid}/add",
        data={**data, "media": (buf, "chart.png")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    with app_obj.app_context():
        ev = TradeReplayEvent.query.filter_by(trade_id=tid).first()
        assert ev is not None
        assert ev.media_filename
        assert "chart" in ev.media_filename.lower() or ev.media_filename.endswith(".png")
        d = os.path.join(tmp_path, "replay")
        assert os.path.isfile(os.path.join(d, ev.media_filename))


def test_replay_rapid_sequential_uploads(app, tmp_path):
    app_obj, uid, tid = app
    app_obj.config["TRADE_SCREENSHOTS_FOLDER"] = str(tmp_path)
    client = app_obj.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)

    for i in range(5):
        buf = io.BytesIO(b"%s fake png" % str(i).encode())
        buf.name = f"x{i}.png"
        r = client.post(
            f"/replay/trade/{tid}/add",
            data={"event_type": "note", "note": f"n{i}", "media": (buf, f"x{i}.png")},
            content_type="multipart/form-data",
        )
        assert r.status_code in (302, 303)

    with app_obj.app_context():
        assert TradeReplayEvent.query.filter_by(trade_id=tid).count() == 5
