#!/usr/bin/env python
"""
Quick test of the instruments API endpoint
"""

from app import create_app, db
from app.models.instrument import Instrument, DEFAULT_INSTRUMENTS

app = create_app('development')

with app.app_context():
    # Ensure instruments are seeded
    if Instrument.query.count() == 0:
        print("Seeding default instruments...")
        for inst_data in DEFAULT_INSTRUMENTS:
            instrument = Instrument(
                symbol=inst_data['symbol'],
                name=inst_data['name'],
                instrument_type=inst_data['type'],
                category=inst_data['category'],
                pip_size=inst_data.get('pip_size', 0.0001),
                tick_value=inst_data.get('tick_value', 1.0),
                contract_size=inst_data.get('contract_size', 1.0),
                price_decimals=inst_data.get('price_decimals', 4)
            )
            db.session.add(instrument)
        db.session.commit()
        print(f"[OK] Seeded {Instrument.query.count()} instruments")
    
    # Test queries
    print("\n=== All Instruments ===")
    for inst in Instrument.query.all():
        print(f"{inst.symbol:10} | {inst.name:30} | {inst.instrument_type}")
    
    print(f"\n=== Total: {Instrument.query.count()} instruments ===")
    
    # Test by category
    print("\n=== By Category ===")
    categories = db.session.query(
        Instrument.category,
        db.func.count(Instrument.id).label('count')
    ).group_by(Instrument.category).all()
    
    for cat, count in categories:
        print(f"{cat:12} - {count} instruments")
    
    # Test search
    print("\n=== Search 'BTC' ===")
    for inst in Instrument.query.filter(
        (Instrument.symbol.ilike('%BTC%')) | 
        (Instrument.name.ilike('%BTC%'))
    ).all():
        print(f"Found: {inst.symbol}")
