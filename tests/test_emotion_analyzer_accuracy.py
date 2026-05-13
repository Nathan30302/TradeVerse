"""EmotionAnalyzer aggregates match hand-checked expectations."""

from datetime import timedelta

import pytest

from app import create_app, db, schema_compat
from app.utils.timeutil import utc_now
from app.models.trade import Trade
from app.models.user import User
from app.services.emotion_analyzer import EmotionAnalyzer


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        u = User(username="emo", email="emo@test.dev")
        u.set_password("password12345")
        db.session.add(u)
        db.session.commit()
        uid = u.id
        now = utc_now()
        trades = [
            Trade(
                user_id=uid,
                symbol="EURUSD",
                trade_type="BUY",
                lot_size=1,
                entry_price=1.1,
                exit_price=1.11,
                status="CLOSED",
                profit_loss=100.0,
                emotion="Confident",
                entry_date=now - timedelta(days=1),
                exit_date=now - timedelta(days=1),
            ),
            Trade(
                user_id=uid,
                symbol="EURUSD",
                trade_type="BUY",
                lot_size=1,
                entry_price=1.1,
                exit_price=1.09,
                status="CLOSED",
                profit_loss=-50.0,
                emotion="Confident",
                entry_date=now - timedelta(days=2),
                exit_date=now - timedelta(days=2),
            ),
            Trade(
                user_id=uid,
                symbol="GBPUSD",
                trade_type="BUY",
                lot_size=1,
                entry_price=1.25,
                exit_price=1.25,
                status="CLOSED",
                profit_loss=0.0,
                emotion="Fearful",
                entry_date=now - timedelta(days=3),
                exit_date=now - timedelta(days=3),
            ),
            Trade(
                user_id=uid,
                symbol="GBPUSD",
                trade_type="SELL",
                lot_size=1,
                entry_price=1.25,
                exit_price=1.26,
                status="CLOSED",
                profit_loss=-20.0,
                emotion="Fearful",
                entry_date=now - timedelta(days=4),
                exit_date=now - timedelta(days=4),
            ),
        ]
        for t in trades:
            db.session.add(t)
        db.session.commit()
        yield app, uid


def test_emotion_performance_win_rate_excludes_breakeven_from_denominator(app):
    app_obj, uid = app
    with app_obj.app_context():
        an = EmotionAnalyzer(uid)
        perf = an.get_emotion_performance(days=90)
        conf = perf["Confident"]
        assert conf["count"] == 2
        assert conf["wins"] == 1 and conf["losses"] == 1
        assert abs(conf["win_rate"] - 50.0) < 1e-6

        fear = perf["Fearful"]
        assert fear["count"] == 2
        assert fear["wins"] == 0 and fear["losses"] == 1
        assert abs(fear["win_rate"] - 0.0) < 1e-6
        assert abs(fear["total_pnl"] - (-20.0)) < 1e-6


def test_emotion_summary_counts(app):
    app_obj, uid = app
    with app_obj.app_context():
        an = EmotionAnalyzer(uid)
        s = an.get_summary(days=90)
        assert s["total_trades_with_emotion"] == 4
