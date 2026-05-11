#!/usr/bin/env python3
"""CLI: time dashboard analytics queries with N synthetic closed trades (dev only)."""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app, db  # noqa: E402
from app.models.trade import Trade  # noqa: E402
from app.models.user import User  # noqa: E402
from sqlalchemy import func  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trades", type=int, default=2000)
    p.add_argument("--config", default="development")
    args = p.parse_args()

    app = create_app(args.config)
    with app.app_context():
        u = User.query.first()
        if not u:
            print("No user in DB; create one first.")
            return 1
        uid = u.id
        Trade.query.filter_by(user_id=uid).delete()
        db.session.commit()
        base = datetime(2022, 1, 1)
        batch = []
        for i in range(args.trades):
            batch.append(
                Trade(
                    user_id=uid,
                    symbol="EURUSD",
                    trade_type="BUY",
                    lot_size=0.1,
                    entry_price=1.1,
                    exit_price=1.11,
                    status="CLOSED",
                    profit_loss=10.0 if i % 2 == 0 else -5.0,
                    strategy="S",
                    session_type="London",
                    emotion="Confident",
                    entry_date=base + timedelta(minutes=i),
                    exit_date=base + timedelta(minutes=i, seconds=30),
                )
            )
            if len(batch) >= 400:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                batch = []
        if batch:
            db.session.bulk_save_objects(batch)
            db.session.commit()

        t0 = time.perf_counter()
        q = (
            db.session.query(
                Trade.symbol,
                func.count(Trade.id),
                func.sum(Trade.profit_loss),
            )
            .filter(Trade.user_id == uid, Trade.status == "CLOSED", Trade.profit_loss.isnot(None))
            .group_by(Trade.symbol)
            .all()
        )
        dt = time.perf_counter() - t0
        print(f"instrument_stats rows={len(q)} time={dt:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
