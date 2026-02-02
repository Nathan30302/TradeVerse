"""
Seed the instruments JSON into the database. Run with Flask app context.
Example:
  python -c "from app import create_app; app = create_app('development'); ctx = app.app_context(); ctx.push(); import scripts.seed_instruments as s; s.seed()"
"""
import json
from app import db
from app.models.instrument import Instrument, InstrumentAlias
from pathlib import Path


def seed(path=None):
    path = path or Path('data') / 'instruments.json'
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)

    count = 0
    for inst in data:
        symbol = inst.get('symbol')
        if not symbol:
            continue
        existing = Instrument.query.filter_by(symbol=symbol).first()
        if existing:
            # still ensure aliases exist in alias table if present
            if 'aliases' in inst and inst['aliases']:
                for a in inst.get('aliases', []):
                    if not InstrumentAlias.query.filter_by(alias=a.upper()).first():
                        ia = InstrumentAlias(instrument_id=existing.id, alias=a.upper())
                        db.session.add(ia)
            continue
        description = inst.get('notes')
        # embed aliases into description JSON for backward compatibility
        if 'aliases' in inst:
            try:
                desc_obj = {'aliases': inst.get('aliases', [])}
                if description:
                    desc_obj['note'] = description
                description = json.dumps(desc_obj)
            except Exception:
                description = None

        instrument = Instrument(
            symbol=symbol,
            name=inst.get('display_name') or inst.get('name') or symbol,
            instrument_type=inst.get('type', 'stock'),
            category=inst.get('type', 'stock'),
            pip_size=inst.get('pip_or_tick_size', inst.get('pip_size', 0.0001)),
            tick_value=inst.get('tick_value', 1.0),
            contract_size=inst.get('contract_size', 1.0),
            price_decimals=inst.get('price_decimals', 2),
            description=description
        )
        db.session.add(instrument)
        db.session.flush()
        # create alias entries in alias table
        if 'aliases' in inst and inst['aliases']:
            for a in inst.get('aliases', []):
                try:
                    ia = InstrumentAlias(instrument_id=instrument.id, alias=a.upper())
                    db.session.add(ia)
                except Exception:
                    pass
        count += 1
        if count % 500 == 0:
            db.session.commit()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    print(f"Seeded instruments: {count}")

if __name__ == '__main__':
    seed()
