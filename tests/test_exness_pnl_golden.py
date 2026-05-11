"""Golden-vector tests for Exness-style P&L (DB-backed instrument metadata)."""

import pytest

from app import create_app, db, schema_compat
from app.models.instrument import Instrument
from app.services.exness_pnl_calculator import calculate_pnl


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        _seed_instruments()
        db.session.commit()
        yield app


def _seed_instruments():
    rows = [
        Instrument(
            symbol="EURUSD",
            name="EUR/USD",
            instrument_type="forex",
            category="Forex",
            pip_size=0.0001,
            contract_size=100000,
            tick_value=10.0,
        ),
        Instrument(
            symbol="USDJPY",
            name="USD/JPY",
            instrument_type="forex",
            category="Forex",
            pip_size=0.01,
            contract_size=100000,
            tick_value=1000.0,
        ),
        Instrument(
            symbol="XAUUSD",
            name="Gold",
            instrument_type="commodity",
            category="Energies",
            pip_size=0.01,
            contract_size=100,
            tick_value=1.0,
        ),
        Instrument(
            symbol="NAS100",
            name="US Tech 100",
            instrument_type="index",
            category="Indices",
            pip_size=0.25,
            contract_size=1,
            tick_value=20.0,
        ),
        Instrument(
            symbol="BTCUSD",
            name="Bitcoin",
            instrument_type="crypto",
            category="Crypto",
            pip_size=0.01,
            contract_size=1,
            tick_value=1.0,
        ),
    ]
    for r in rows:
        db.session.add(r)


def test_forex_eurusd_buy_pips_and_pnl(app):
    with app.app_context():
        pnl, pips, method = calculate_pnl(
            symbol="EURUSD",
            trade_type="BUY",
            entry_price=1.1000,
            exit_price=1.1050,
            lot_size=1.0,
        )
        assert method == "forex"
        assert abs(pnl - 500.0) < 0.02
        assert abs(pips - 50.0) < 0.2


def test_forex_commission_and_swap(app):
    with app.app_context():
        pnl, _, _ = calculate_pnl(
            symbol="EURUSD",
            trade_type="BUY",
            entry_price=1.1000,
            exit_price=1.1050,
            lot_size=1.0,
            commission=12.5,
            swap=-3.25,
        )
        assert abs(pnl - (500.0 - 12.5 - 3.25)) < 0.02


def test_metal_xauusd(app):
    with app.app_context():
        pnl, _, method = calculate_pnl(
            symbol="XAUUSD",
            trade_type="BUY",
            entry_price=2000.0,
            exit_price=2010.0,
            lot_size=1.0,
        )
        assert method == "commodity"
        assert abs(pnl - 1000.0) < 0.02


def test_index_nas100(app):
    with app.app_context():
        pnl, _, method = calculate_pnl(
            symbol="NAS100",
            trade_type="BUY",
            entry_price=25214.37,
            exit_price=25181.07,
            lot_size=0.03,
        )
        assert method == "index"
        assert abs(pnl - (-33.3 * 20.0 * 0.03)) < 0.05


def test_crypto_btcusd(app):
    with app.app_context():
        pnl, _, method = calculate_pnl(
            symbol="BTCUSD",
            trade_type="BUY",
            entry_price=104568.99,
            exit_price=104351.28,
            lot_size=0.01,
        )
        assert method == "crypto"
        assert abs(pnl - (-2.1771)) < 0.02
