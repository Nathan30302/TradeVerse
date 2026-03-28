#!/usr/bin/env python3
"""
P&L Validation Test Script
Tests P&L calculations against expected values from user requirements
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.utils.pnl_calculator import calculate_pnl

# Test cases from user requirements
test_cases = [
    {
        'name': 'USDJPY',
        'symbol': 'USDJPY',
        'trade_type': 'BUY',
        'entry': 155.057,
        'exit': 155.995,
        'lot_size': 0.01,
        'expected': 60.0,
        'tolerance': 5.0
    },
    {
        'name': 'NAS100',
        'symbol': 'NAS100',
        'trade_type': 'BUY',
        'entry': 25214.37,
        'exit': 25181.07,
        'lot_size': 0.03,
        'expected': -9.99,
        'tolerance': 1.0
    },
    {
        'name': 'USDCAD',
        'symbol': 'USDCAD',
        'trade_type': 'SELL',
        'entry': 1.39813,
        'exit': 1.39760,
        'lot_size': 0.40,
        'expected': 15.17,
        'tolerance': 3.0
    },
    {
        'name': 'BTCUSD',
        'symbol': 'BTCUSD',
        'trade_type': 'BUY',
        'entry': 104568.99,
        'exit': 104351.28,
        'lot_size': 0.01,
        'expected': -2.18,
        'tolerance': 0.5
    },
    {
        'name': 'ETHUSD',
        'symbol': 'ETHUSD',
        'trade_type': 'BUY',
        'entry': 46489.71,
        'exit': 46430.63,
        'lot_size': 0.30,
        'expected': -17.72,
        'tolerance': 2.0
    }
]

print("\n" + "="*80)
print("P&L CALCULATION VALIDATION TEST")
print("="*80)
print(f"{'Symbol':<12} {'Type':<6} {'Entry':>12} {'Exit':>12} {'Lot':>8} {'Expected':>12} {'Calculated':>12} {'Diff':>10} {'Status':>10}")
print("-"*80)

all_passed = True
for tc in test_cases:
    pnl, pips, desc = calculate_pnl(
        tc['symbol'],
        tc['trade_type'],
        tc['entry'],
        tc['exit'],
        tc['lot_size']
    )
    
    diff = abs(pnl - tc['expected'])
    passed = diff <= tc['tolerance']
    all_passed = all_passed and passed
    
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{tc['symbol']:<12} {tc['trade_type']:<6} {tc['entry']:>12.5f} {tc['exit']:>12.5f} {tc['lot_size']:>8.2f} "
          f"${tc['expected']:>10.2f} ${pnl:>10.2f} ${diff:>8.2f} {status:>10}")

print("="*80)
if all_passed:
    print("✅ ALL TESTS PASSED")
else:
    print("❌ SOME TESTS FAILED - Calculation logic needs adjustment")
print("="*80 + "\n")

