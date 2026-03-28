#!/usr/bin/env python3
"""
Test instrument mapping with sample broker symbols.
Generates a report of mapped/unmapped symbols for each broker.

Usage: python scripts/seed_instrument_mapper.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_mapping():
    """Test mapping for various broker symbol formats."""
    from app.mappers.instrument_mapper import mapper, map_broker_symbol
    
    test_cases = {
        'oanda': [
            'EUR_USD', 'GBP_USD', 'USD_JPY', 'XAU_USD', 'XAG_USD',
            'SPX500_USD', 'NAS100_USD', 'US30_USD', 'BCO_USD', 'WTICO_USD',
            'DE30_EUR', 'UK100_GBP', 'JP225_USD'
        ],
        'binance': [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT',
            'SOLUSDT', 'DOGEUSDT', 'DOTUSDT', 'MATICUSDT', 'ETHBTC'
        ],
        'xm': [
            'EURUSDm', 'GBPUSDm', 'GOLD', 'GOLDm', 'SILVER',
            'US500', 'US500m', 'GER30', 'UK100', 'OIL'
        ],
        'mt4_generic': [
            'EURUSD', 'GBPUSD.ecn', 'USDJPY', 'XAUUSD.pro', 'XAGUSD',
            'US500', 'NAS100', 'GER40', 'BTCUSD'
        ],
        'pepperstone': [
            'EURUSD', 'EURUSD.m', 'GBPUSD', 'XAUUSD', 'XAUUSD.m',
            'US500', 'US500.m', 'NAS100', 'NAS100.m', 'XBRUSD', 'XTIUSD'
        ],
        'ibkr': [
            'EUR.USD', 'GBP.USD', 'AAPL', 'MSFT', 'GOOGL',
            'ES', 'NQ', 'YM', 'GC', 'SI', 'CL'
        ],
        'ig': [
            'CS.D.EURUSD.CFD.IP', 'CS.D.GBPUSD.CFD.IP',
            'IX.D.FTSE.DAILY.IP', 'IX.D.DAX.DAILY.IP',
            'CC.D.CL.USS.IP'
        ]
    }
    
    print("=" * 80)
    print("INSTRUMENT MAPPING TEST REPORT")
    print("=" * 80)
    
    overall_mapped = 0
    overall_total = 0
    
    for broker_id, symbols in test_cases.items():
        report = mapper.get_mapping_report(symbols, broker_id)
        
        print(f"\n{broker_id.upper()}")
        print("-" * 40)
        print(f"Total: {report['total_symbols']}")
        print(f"Mapped: {report['mapped_count']} ({report['mapping_rate']*100:.1f}%)")
        print(f"Unmapped: {report['unmapped_count']}")
        print(f"Low confidence: {report['low_confidence_count']}")
        
        overall_mapped += report['mapped_count']
        overall_total += report['total_symbols']
        
        if report['unmapped']:
            print("\nUnmapped symbols:")
            for item in report['unmapped']:
                print(f"  - {item['original']} -> {item['canonical']} (conf: {item['confidence']:.2f})")
        
        if report['low_confidence']:
            print("\nLow confidence mappings:")
            for item in report['low_confidence']:
                print(f"  - {item['original']} -> {item['canonical']} (conf: {item['confidence']:.2f})")
    
    print("\n" + "=" * 80)
    print(f"OVERALL: {overall_mapped}/{overall_total} mapped ({overall_mapped/overall_total*100:.1f}%)")
    print("=" * 80)


if __name__ == '__main__':
    test_mapping()
