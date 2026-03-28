#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.utils.pnl_calculator import detect_asset_type, calculate_pnl

# Test various symbols
test_symbols = ['USDJPY', 'NAS100', 'USDCAD', 'BTCUSD', 'ETHUSD', 'XAUUSD', 'XAGUSD', 'EURUSD', 'GBPUSD']

print('Symbol Detection Test:')
for symbol in test_symbols:
    asset_type = detect_asset_type(symbol)
    print(f'{symbol:8} -> {asset_type.value}')

print('\nP&L Calculation Test (BUY 100->101, 0.01 lot):')
for symbol in test_symbols:
    pnl, pips, desc = calculate_pnl(symbol, 'BUY', 100, 101, 0.01)
    print(f'{symbol:8} -> ${pnl:8.2f} ({desc})')
