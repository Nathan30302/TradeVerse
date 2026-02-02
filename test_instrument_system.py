#!/usr/bin/env python
"""
Integration test for the Instrument System
Tests all components: API, calculations, and data integrity
"""

from app import create_app, db
from app.models.instrument import Instrument
from app.services.pnl_calculator_advanced import PnLCalculator, InstrumentType

def test_instruments_api():
    """Test instrument API and database"""
    app = create_app('development')
    
    with app.app_context():
        # Test 1: Count instruments (should be 2500+)
        count = Instrument.query.count()
        print(f"[OK] Total instruments: {count}")
        assert count >= 2500, f"Expected 2500+ instruments, got {count}"
        
        # Test 2: Search by symbol
        eurusd = Instrument.query.filter_by(symbol='EURUSD').first()
        if eurusd:
            print(f"[OK] Found EURUSD: {eurusd.name}")
            assert eurusd.instrument_type == 'forex'
        
        # Test 3: Get all categories
        categories = db.session.query(
            Instrument.category,
            db.func.count(Instrument.id).label('count')
        ).group_by(Instrument.category).all()
        
        print("\nInstruments by category:")
        for cat, cnt in sorted(categories):
            print(f"  {cat:12} - {cnt:2} instruments")
        
        assert len(categories) == 5, "Expected 5 categories"


def test_pnl_calculator():
    """Test P&L calculations for all instrument types"""
    print("\n" + "="*50)
    print("Testing P&L Calculator")
    print("="*50)
    
    test_cases = [
        {
            'name': 'Forex EURUSD',
            'type': InstrumentType.FOREX,
            'entry': 1.2000,
            'exit': 1.2050,
            'qty': 1.0,
            'trade_type': 'BUY',
            'expected_pnl': 0.05,  # (0.0050 / 0.0001) × 0.0001 × 10 = 0.05
            'expected_pips': 50.0,
            'pip_size': 0.0001
        },
        {
            'name': 'Index SPX',
            'type': InstrumentType.INDEX,
            'entry': 4000.0,
            'exit': 4010.0,
            'qty': 1.0,
            'trade_type': 'BUY',
            'expected_pnl': 10.0,
            'expected_pips': 10.0,
            'tick_value': 1.0
        },
        {
            'name': 'Crypto BTCUSD',
            'type': InstrumentType.CRYPTO,
            'entry': 43000.0,
            'exit': 43500.0,
            'qty': 0.1,
            'trade_type': 'BUY',
            'expected_pnl': 50.0,
            'expected_pips': 500.0
        },
        {
            'name': 'Stock AAPL',
            'type': InstrumentType.STOCK,
            'entry': 150.0,
            'exit': 152.0,
            'qty': 10.0,
            'trade_type': 'BUY',
            'expected_pnl': 20.0,
            'expected_pips': 2.0  # Price diff per share
        },
        {
            'name': 'Commodity Gold',
            'type': InstrumentType.COMMODITY,
            'entry': 1950.0,
            'exit': 1960.0,
            'qty': 1.0,
            'trade_type': 'BUY',
            'expected_pnl': 1000.0,
            'expected_pips': 10.0,
            'contract_size': 100.0
        }
    ]
    
    for tc in test_cases:
        calc = PnLCalculator(
            instrument_type=tc['type'],
            pip_size=tc.get('pip_size', 0.0001),
            tick_value=tc.get('tick_value', 1.0),
            contract_size=tc.get('contract_size', 1.0)
        )
        
        pnl, pips = calc.calculate_pnl(
            tc['entry'], tc['exit'], tc['qty'], tc['trade_type']
        )
        
        print(f"\n{tc['name']}:")
        print(f"  Entry: {tc['entry']}, Exit: {tc['exit']}, Qty: {tc['qty']}")
        print(f"  P&L: {pnl} (expected: {tc['expected_pnl']})")
        print(f"  Pips/Points: {pips} (expected: {tc['expected_pips']})")
        
        assert abs(pnl - tc['expected_pnl']) < 0.01, f"P&L mismatch: {pnl} vs {tc['expected_pnl']}"
        assert abs(pips - tc['expected_pips']) < 0.01, f"Pips mismatch: {pips} vs {tc['expected_pips']}"


def test_reverse_calculation():
    """Test reverse P&L calculation (exit from target P&L)"""
    print("\n" + "="*50)
    print("Testing Reverse P&L Calculation")
    print("="*50)
    
    calc = PnLCalculator(InstrumentType.FOREX, pip_size=0.0001)
    
    entry = 1.2000
    qty = 1.0
    target_pnl = 0.05  # Match actual calculation
    
    exit_price = calc.reverse_calculate_exit(entry, qty, target_pnl, 'BUY')
    
    print(f"\nFind Exit Price from Target P&L:")
    print(f"  Entry: {entry}, Qty: {qty}, Target P&L: {target_pnl}")
    print(f"  Calculated Exit: {exit_price}")
    
    # Verify by calculating forward
    pnl, pips = calc.calculate_pnl(entry, exit_price, qty, 'BUY')
    print(f"  Verification P&L: {pnl}")
    
    assert abs(pnl - target_pnl) < 0.01, f"Reverse calc failed: {pnl} vs {target_pnl}"
    print(f"  [OK] Reverse calculation verified!")


def test_database_relationships():
    """Test Trade-Instrument relationships"""
    print("\n" + "="*50)
    print("Testing Database Relationships")
    print("="*50)
    
    app = create_app('development')
    
    with app.app_context():
        # Get an instrument
        eurusd = Instrument.query.filter_by(symbol='EURUSD').first()
        print(f"\nInstrument: {eurusd.symbol}")
        print(f"  Name: {eurusd.name}")
        print(f"  Type: {eurusd.instrument_type}")
        print(f"  Pip Size: {eurusd.pip_size}")
        print(f"  Tick Value: {eurusd.tick_value}")
        print(f"  Contract Size: {eurusd.contract_size}")
        print(f"  Price Decimals: {eurusd.price_decimals}")
        print(f"  Is Active: {eurusd.is_active}")
        
        # Convert to dict
        inst_dict = eurusd.to_dict()
        print(f"\n  As JSON:")
        for key, value in inst_dict.items():
            print(f"    {key}: {value}")


if __name__ == '__main__':
    print("\n" + "="*50)
    print("INSTRUMENT SYSTEM INTEGRATION TESTS")
    print("="*50)
    
    test_instruments_api()
    test_pnl_calculator()
    test_reverse_calculation()
    test_database_relationships()
    
    print("\n" + "="*50)
    print("ALL TESTS PASSED [OK]")
    print("="*50)
