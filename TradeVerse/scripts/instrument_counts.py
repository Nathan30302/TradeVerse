from app import create_app, db
from app.models.instrument import Instrument

app = create_app()
with app.app_context():
    total = Instrument.query.filter(Instrument.is_active==True).count()
    print(f"Total active instruments: {total}")
    rows = Instrument.query.with_entities(Instrument.category, db.func.count(Instrument.id)).filter(Instrument.is_active==True).group_by(Instrument.category).all()
    print('Counts by category:')
    for cat, cnt in rows:
        print(f"  {cat}: {cnt}")
    # also show sample tail
    print('\nSample last symbols (by symbol):')
    last = Instrument.query.order_by(Instrument.symbol.desc()).limit(20).all()
    for inst in last:
        print(inst.symbol)
