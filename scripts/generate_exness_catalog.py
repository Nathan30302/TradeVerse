"""Generate an Exness-like instrument catalog JSON

Produces a catalog matching these sector counts:
- Crypto Cross – 6
- Crypto – 29
- Energies – 3
- Forex – 140
- Indices – 11
- Stocks – 101
- IDX-Large – 3
- Forex Indicator – 55

This is synthetic but uses realistic symbol/name templates. Output written to
`data/exness_full_catalog.json` which can be loaded with `scripts/load_instruments.py`.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'data' / 'exness_full_catalog.json'

# small helper generators
def gen_forex_pairs(n):
    base_currencies = ['EUR','GBP','USD','JPY','AUD','CAD','CHF','NZD','SEK','NOK','DKK','SGD']
    quote_currencies = ['USD','JPY','EUR','GBP','AUD','CAD','CHF','NZD']
    pairs = []
    i = 0
    for b in base_currencies:
        for q in quote_currencies:
            if b == q:
                continue
            pairs.append({'symbol': f'{b}{q}', 'base': b, 'quote': q})
            i += 1
            if i >= n:
                return pairs
    # if still short, generate synthetic pairs
    while len(pairs) < n:
        pairs.append({'symbol': f'F{len(pairs)}USD', 'base': f'F{len(pairs)}', 'quote': 'USD'})
    return pairs

def gen_crypto(n, cross=False):
    cores = ['BTC','ETH','LTC','XRP','BCH','DOT','ADA','SOL','LINK','AVAX','DOGE','MATIC','BNB','TRX','XLM','ATOM','VET']
    out = []
    i = 0
    while len(out) < n:
        sym = cores[i % len(cores)]
        if cross:
            symbol = f'{sym}USD' if i % 2 == 0 else f'{sym}BTC'
        else:
            symbol = f'{sym}USD'
        out.append({'symbol': symbol, 'base': sym, 'quote': 'USD' if 'USD' in symbol else 'BTC'})
        i += 1
    return out

def gen_indices(n):
    known = ['US500','US100','US30','DE30','UK100','JP225','AUS200','SPX','NDX','HK50','CN50']
    out = []
    for i in range(n):
        sym = known[i] if i < len(known) else f'IDX{i}'
        out.append({'symbol': sym, 'name': f'{sym} Index'})
    return out

def gen_energies():
    return [
        {'symbol':'XAUUSD','name':'Gold / US Dollar','instrument_type':'commodity'},
        {'symbol':'XAGUSD','name':'Silver / US Dollar','instrument_type':'commodity'},
        {'symbol':'WTIUSD','name':'WTI Crude Oil','instrument_type':'commodity'}
    ]

def gen_stocks(n):
    common = ['AAPL','MSFT','GOOGL','AMZN','TSLA','NVDA','META','INTC','CSCO','ORCL','IBM','BA','JNJ','PG','KO','PEP','DIS','ADBE','CRM','PYPL','NFLX']
    out = []
    i = 0
    while len(out) < n:
        sym = common[i % len(common)]
        if i >= len(common):
            sym = f'{sym}{(i//len(common))}'
        out.append({'symbol': sym, 'name': f'{sym} Corp'})
        i += 1
    return out

# Build catalog
catalog = {'meta': {'source':'synthetic-exness','created_at':'2026-02-23T00:00:00Z'}, 'instruments': []}

# Forex (140)
for p in gen_forex_pairs(140):
    catalog['instruments'].append({
        'symbol': p['symbol'],
        'name': f"{p['base']} / {p['quote']}",
        'instrument_type': 'forex',
        'category': 'Forex',
        'pip_size': 0.01 if p['quote']=='JPY' else 0.0001,
        'contract_size': 100000,
        'price_decimals': 5 if p['quote']!='JPY' else 3,
        'base_currency': p['base'],
        'quote_currency': p['quote'],
        'lot_min': 0.01,
        'lot_max': 100,
        'lot_step': 0.01,
        'tick_size': 0.00001 if p['quote']!='JPY' else 0.01,
        'margin_rate': 0.02,
        'pnl_method': 'forex'
    })

# Forex Indicator (55) - generate synthetic indicator symbols
for i in range(55):
    sym = f'FIND{i+1}'
    catalog['instruments'].append({
        'symbol': sym,
        'name': f'Forex Indicator {i+1}',
        'instrument_type': 'forex_indicator',
        'category': 'Forex Indicator',
        'pip_size': 0.0001,
        'contract_size': 100000,
        'price_decimals': 5,
        'base_currency': 'USD',
        'quote_currency': 'USD',
        'lot_min': 0.01,
        'lot_max': 100,
        'lot_step': 0.01,
        'tick_size': 0.00001,
        'margin_rate': 0.02,
        'pnl_method': 'forex'
    })

# Crypto Cross (6)
for rec in gen_crypto(6, cross=True):
    catalog['instruments'].append({
        'symbol': rec['symbol'],
        'name': f"{rec['base']} / {rec['quote']}",
        'instrument_type': 'crypto',
        'category': 'Crypto Cross',
        'pip_size': 0.01,
        'contract_size': 1,
        'price_decimals': 2,
        'base_currency': rec['base'],
        'quote_currency': rec['quote'],
        'lot_min': 0.0001,
        'lot_max': 100,
        'lot_step': 0.0001,
        'tick_size': 0.01,
        'margin_rate': 0.5,
        'pnl_method': 'crypto'
    })

# Crypto (29)
for rec in gen_crypto(29, cross=False):
    catalog['instruments'].append({
        'symbol': rec['symbol'],
        'name': f"{rec['base']} / {rec['quote']}",
        'instrument_type': 'crypto',
        'category': 'Crypto',
        'pip_size': 0.01,
        'contract_size': 1,
        'price_decimals': 2,
        'base_currency': rec['base'],
        'quote_currency': rec['quote'],
        'lot_min': 0.0001,
        'lot_max': 100,
        'lot_step': 0.0001,
        'tick_size': 0.01,
        'margin_rate': 0.5,
        'pnl_method': 'crypto'
    })

# Indices (11)
for rec in gen_indices(11):
    catalog['instruments'].append({
        'symbol': rec['symbol'],
        'name': rec['name'],
        'instrument_type': 'index',
        'category': 'Indices',
        'pip_size': 0.01,
        'contract_size': 10,
        'price_decimals': 2,
        'base_currency': None,
        'quote_currency': 'USD',
        'lot_min': 0.01,
        'lot_max': 100,
        'lot_step': 0.01,
        'tick_size': 0.01,
        'margin_rate': 0.05,
        'pnl_method': 'index'
    })

# IDX-Large (3) - large indices
for sym in ['US30L','EU50L','ASIA50L']:
    catalog['instruments'].append({
        'symbol': sym,
        'name': f'{sym} Large Index',
        'instrument_type': 'index',
        'category': 'IDX-Large',
        'pip_size': 0.1,
        'contract_size': 100,
        'price_decimals': 2,
        'base_currency': None,
        'quote_currency': 'USD',
        'lot_min': 0.01,
        'lot_max': 100,
        'lot_step': 0.01,
        'tick_size': 0.1,
        'margin_rate': 0.05,
        'pnl_method': 'index'
    })

# Energies (3)
for rec in gen_energies():
    catalog['instruments'].append({
        'symbol': rec['symbol'],
        'name': rec['name'],
        'instrument_type': 'commodity',
        'category': 'Energies',
        'pip_size': 0.01,
        'contract_size': 100 if 'XAU' in rec['symbol'] else 1000,
        'price_decimals': 2,
        'base_currency': rec['symbol'][:3],
        'quote_currency': 'USD',
        'lot_min': 0.01,
        'lot_max': 100,
        'lot_step': 0.01,
        'tick_size': 0.01,
        'margin_rate': 0.02,
        'pnl_method': 'commodity'
    })

# Stocks (101)
for rec in gen_stocks(101):
    catalog['instruments'].append({
        'symbol': rec['symbol'],
        'name': rec['name'],
        'instrument_type': 'stock',
        'category': 'Stocks',
        'pip_size': 0.01,
        'contract_size': 1,
        'price_decimals': 2,
        'base_currency': rec['symbol'],
        'quote_currency': 'USD',
        'lot_min': 1,
        'lot_max': 100000,
        'lot_step': 1,
        'tick_size': 0.01,
        'margin_rate': 0.05,
        'pnl_method': 'stock'
    })

# Sanity check count
assert len(catalog['instruments']) >= (6+29+3+140+11+101+3+55), f"catalog too small: {len(catalog['instruments'])}"

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(catalog, indent=2))
print(f'Wrote {OUT} with {len(catalog["instruments"])} instruments')
