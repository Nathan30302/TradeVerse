import pytest
from app.services.pnl_engine import calculate_pnl


def test_forex_pnl():
    meta = {'type':'forex','pip_or_tick_size':0.0001,'tick_value':0.0001,'contract_size':100000}
    res = calculate_pnl('EURUSD', meta, 1.1000, 1.1050, 1, size_type='lots')
    assert 'pnl' in res
    assert res['pip_move'] == pytest.approx(50.0, rel=1e-3)


def test_index_pnl():
    meta = {'type':'index','tick_value':1.0}
    res = calculate_pnl('SPX', meta, 4000, 4010, 2)
    assert res['pnl'] == 20.0


def test_crypto_pnl_units():
    meta = {'type':'crypto','contract_size':1}
    # (21000 - 20000) * 0.1 = 1000 * 0.1 = 100.0
    res = calculate_pnl('BTCUSD', meta, 20000, 21000, 0.1, size_type='units')
    assert res['pnl'] == pytest.approx(100.0)


def test_stock_pnl():
    meta = {'type':'stock'}
    res = calculate_pnl('AAPL', meta, 150, 155, 10, size_type='units')
    assert res['pnl'] == 50.0


def test_commodity_pnl():
    meta = {'type':'commodity','contract_size':100}
    res = calculate_pnl('XAUUSD', meta, 1800, 1810, 1)
    assert res['pnl'] == 1000.0
