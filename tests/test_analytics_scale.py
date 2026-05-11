"""Analytics and advanced metrics stay within time budget with many closed trades."""

import time
from datetime import datetime, timedelta

import pytest

from app import create_app, db, schema_compat
from app.models.trade import Trade
from app.models.user import User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        u = User(username="scale", email="scale@test.dev")
        u.set_password("password12345")
        db.session.add(u)
        db.session.commit()
        uid = u.id
        base = datetime(2023, 1, 1)
        chunk = []
        for i in range(2500):
            chunk.append(
                Trade(
                    user_id=uid,
                    symbol="EURUSD" if i % 2 == 0 else "GBPUSD",
                    trade_type="BUY",
                    lot_size=0.1,
                    entry_price=1.1,
                    exit_price=1.11 if i % 3 else 1.09,
                    status="CLOSED",
                    profit_loss=25.0 if i % 3 else -12.0,
                    strategy="Scalp" if i % 2 else "Swing",
                    session_type="London",
                    emotion="Confident" if i % 4 else "Neutral",
                    entry_date=base + timedelta(hours=i),
                    exit_date=base + timedelta(hours=i, minutes=30),
                    stop_loss=1.05,
                    take_profit=1.15,
                )
            )
            if len(chunk) >= 500:
                db.session.bulk_save_objects(chunk)
                db.session.commit()
                chunk = []
        if chunk:
            db.session.bulk_save_objects(chunk)
            db.session.commit()
        yield app, uid


def test_analytics_group_queries_fast(app):
    app_obj, uid = app
    client = app_obj.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)

    t0 = time.perf_counter()
    r = client.get("/dashboard/analytics")
    dt = time.perf_counter() - t0
    assert r.status_code == 200
    assert dt < 5.0, f"analytics page too slow: {dt:.2f}s"


def test_advanced_metrics_api_fast(app):
    app_obj, uid = app
    client = app_obj.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)

    t0 = time.perf_counter()
    r = client.get("/dashboard/api/advanced-metrics")
    dt = time.perf_counter() - t0
    assert r.status_code in (200, 302, 403)
    if r.status_code == 200:
        assert dt < 6.0, f"advanced metrics too slow: {dt:.2f}s"
        data = r.get_json()
        assert data.get("count_closed", 0) >= 2000
