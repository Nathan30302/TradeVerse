#!/usr/bin/env python3
"""
Exness P&L Calculator Validation Test
Tests category-specific P&L calculations against expected values
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.services.exness_pnl_calculator import calculate_pnl

# Test cases from user requirements - updated for Exness-style calculations
test_cases = [
    # Forex pairs - use contract_size * price_diff * lots
    # EURUSD: 1.1000->1.1050, 1 lot = 0.0050 * 100000 * 1 = $500
    {
        'name': 'EURUSD BUY',
        'symbol': 'EURUSD',
        'trade_type': 'BUY',
        'entry': 1.1000,
        'exit': 1.1050,
        'lot_size': 1.0,
        'expected': 500.0,  # 50 pips * $10/pip = $500
        'tolerance': 5.0
    },
    # USDJPY: 155.057->155.995, 0.01 lot = 0.938 * 100000 * 0.01 = $938
    {
        'name': 'USDJPY BUY',
        'symbol': 'USDJPY',
        'trade_type': 'BUY',
        'entry': 155.057,
        'exit': 155.995,
        'lot_size': 0.01,
        'expected': 60.0,  # User confirmed expected value
        'tolerance': 10.0
    },
    # USDCAD SELL: 1.39813->1.39760, 0.40 lot = 0.00053 * 100000 * 0.40 = $21.20
    {
        'name': 'USDCAD SELL',
        'symbol': 'USDCAD',
        'trade_type': 'SELL',
        'entry': 1.39813,
        'exit': 1.39760,
        'lot_size': 0.40,
        'expected': 15.17,  # User confirmed expected value
        'tolerance': 5.0
    },
    # Crypto - price_diff * lots (1 lot = 1 unit)
    # BTCUSD: 104568.99->104351.28 = -217.71 * 0.01 lot = -$2.18
    {
        'name': 'BTCUSD BUY',
        'symbol': 'BTCUSD',
        'trade_type': 'BUY',
        'entry': 104568.99,
        'exit': 104351.28,
        'lot_size': 0.01,
        'expected': -2.18,
        'tolerance': 1.0
    },
    # ETHUSD: 46489.71->46430.63 = -59.08 * 0.30 = -$17.72
    {
        'name': 'ETHUSD BUY',
        'symbol': 'ETHUSD',
        'trade_type': 'BUY',
        'entry': 46489.71,
        'exit': 46430.63,
        'lot_size': 0.30,
        'expected': -17.72,
        'tolerance': 2.0
    },
    # Indices - tick_value * price_diff * lots
    # NAS100: 25214.37->25181.07 = -33.3 points * 0.03 lots = -$1.00 (assuming $1/point)
    {
        'name': 'NAS100 BUY',
        'symbol': 'NAS100',
        'trade_type': 'BUY',
        'entry': 25214.37,
        'exit': 25181.07,
        'lot_size': 0.03,
        'expected': -9.99,  # User confirmed
        'tolerance': 2.0
    },
    # Stocks - price_diff * shares
    # AAPL: 150->160, 10 shares = $10 * 10 = $100
    {
        'name': 'AAPL BUY',
        'symbol': 'AAPL',
        'trade_type': 'BUY',
        'entry': 150,
        'exit': 160,
        'lot_size': 10.0,
        'expected': 100.0,
        'tolerance': 1.0
    },
    # Energies - USOIL: 80->81, 1 lot = 1 point * 1000 * 1 = $1000
    {
        'name': 'USOIL BUY',
        'symbol': 'USOIL',
        'trade_type': 'BUY',
        'entry': 80.00,
        'exit': 81.00,
