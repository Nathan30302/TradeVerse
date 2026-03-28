"""CLI: load instruments JSON into DB

Usage:
    python scripts/load_instruments.py data/exness_sample_instruments.json

This script reads a JSON file with instrument records and inserts or updates
instruments in the `instruments` table using the SQLAlchemy models.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app, db
from app.models.instrument import Instrument


def load(file_path):
    app = create_app('default')
    with app.app_context():
        p = Path(file_path)
        if not p.exists():
            print(f"File not found: {file_path}")
            return 1
        data = json.loads(p.read_text())
        instruments = data.get('instruments', [])
        for rec in instruments:
            sym = rec.get('symbol')
            if not sym:
                continue
            inst = Instrument.query.filter(Instrument.symbol == sym).first()
            if not inst:
                inst = Instrument(symbol=sym)
            inst.name = rec.get('name') or inst.name
            inst.instrument_type = rec.get('instrument_type') or inst.instrument_type or 'forex'
            inst.category = rec.get('category') or inst.category or 'other'
            inst.pip_size = rec.get('pip_size') or inst.pip_size
            inst.contract_size = rec.get('contract_size') or inst.contract_size
            inst.price_decimals = rec.get('price_decimals') or inst.price_decimals
            inst.base_currency = rec.get('base_currency') or inst.base_currency
            inst.quote_currency = rec.get('quote_currency') or inst.quote_currency
            inst.lot_min = rec.get('lot_min') or inst.lot_min
            inst.lot_max = rec.get('lot_max') or inst.lot_max
            inst.lot_step = rec.get('lot_step') or inst.lot_step
            inst.tick_size = rec.get('tick_size') or inst.tick_size
            inst.margin_rate = rec.get('margin_rate') or inst.margin_rate
            inst.pnl_method = rec.get('pnl_method') or inst.pnl_method
            inst.is_active = True
            db.session.add(inst)
        db.session.commit()
        print(f"Loaded {len(instruments)} instruments from {file_path}")
        return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scripts/load_instruments.py <path-to-json>")
        sys.exit(1)
    sys.exit(load(sys.argv[1]))
