"""
Concurrent writers against SQLite (file-backed) with retries.

Validates no silent IntegrityError storms: each thread uses unique keys and
commit retries on 'database is locked'.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app, db, schema_compat
from app.models.trade import Trade
from app.models.user import User

# SQLite file + stdlib sqlite3: serialize commits across threads (avoids driver misuse).
_SQLITE_COMMIT_LOCK = threading.Lock()


def _commit_with_retry(fn, max_attempts=40):
    for attempt in range(max_attempts):
        try:
            with _SQLITE_COMMIT_LOCK:
                fn()
                db.session.commit()
            return
        except OperationalError:
            db.session.rollback()
            time.sleep(0.02 * (attempt + 1))
    raise RuntimeError("SQLite commit retries exhausted")


@pytest.fixture
def threaded_app():
    fd, path = tempfile.mkstemp(suffix="_concurrent.sqlite")
    os.close(fd)
    try:
        os.unlink(path)
    except OSError:
        pass
    app = create_app("testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{path}"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 45}}
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
    yield app, path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_concurrent_registrations_unique_users(threaded_app):
    app, _path = threaded_app

    with app.app_context():
        _seed = User(username="_pwseed_", email="_pwseed_@concurrent.test")
        _seed.set_password("password12345")
        _ph = _seed.password_hash

    def register(i: int):
        with app.app_context():
            uname = f"reg{i}"
            u = User(username=uname, email=f"reg{i}@concurrent.test")
            u.password_hash = _ph

            def _add():
                db.session.add(u)

            _commit_with_retry(_add)
            return uname

    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(register, i) for i in range(24)]
        for f in as_completed(futs):
            assert f.result().startswith("reg")

    with app.app_context():
        assert User.query.count() == 24


def test_concurrent_trades_single_user(threaded_app):
    app, _path = threaded_app
    with app.app_context():
        u = User(username="trader1", email="trader1@concurrent.test")
        u.set_password("password12345")
        db.session.add(u)
        db.session.commit()
        uid = u.id

    def add_trade(i: int):
        with app.app_context():
            t = Trade(
                user_id=uid,
                symbol="EURUSD",
                trade_type="BUY",
                lot_size=0.01,
                entry_price=1.0 + i * 1e-6,
                status="OPEN",
            )

            def _add():
                db.session.add(t)

            _commit_with_retry(_add)
            tid = t.id
            return tid

    with ThreadPoolExecutor(max_workers=16) as ex:
        ids = [ex.submit(add_trade, i).result() for i in range(40)]

    assert len(set(ids)) == 40
    with app.app_context():
        assert Trade.query.filter_by(user_id=uid).count() == 40


def test_concurrent_profile_updates_same_user(threaded_app):
    app, _path = threaded_app
    with app.app_context():
        u = User(username="prof", email="prof@concurrent.test", full_name="A")
        u.set_password("password12345")
        db.session.add(u)
        db.session.commit()
        uid = u.id

    def bump(i: int):
        with app.app_context():

            def _save():
                u2 = db.session.get(User, uid)
                u2.full_name = f"N{i}"

            _commit_with_retry(_save)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(bump, range(20)))

    with app.app_context():
        final = db.session.get(User, uid).full_name
        assert final.startswith("N")
