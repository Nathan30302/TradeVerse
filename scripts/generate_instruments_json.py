"""
Generate a large instruments JSON file (2,500+ entries) programmatically.
Run this script from the project root to create/overwrite data/instruments.json
"""
import json
from pathlib import Path

OUT = Path('data') / 'instruments.json'

base = [
    {
        "symbol": "EURUSD",
        "display_name": "Euro / US Dollar (EURUSD)",
        "type": "forex",
        "aliases": ["EURUSD", "EUR/USD", "EUR"],
        "pip_or_tick_size": 0.0001,
        "tick_value": 0.0001,
        "contract_size": 100000,
        "price_decimals": 5,
        "notes": "Major forex pair"
    },
    {
        "symbol": "GBPUSD",
        "display_name": "British Pound / US Dollar (GBPUSD)",
        "type": "forex",
        "aliases": ["GBPUSD", "GBP/USD", "GBP"],
        "pip_or_tick_size": 0.0001,
        "tick_value": 0.0001,
        "contract_size": 100000,
        "price_decimals": 5,
        "notes": "Major forex pair"
    },
    {
        "symbol": "USDJPY",
        "display_name": "US Dollar / Japanese Yen (USDJPY)",
        "type": "forex",
        "aliases": ["USDJPY", "USD/JPY", "JPY"],
        "pip_or_tick_size": 0.01,
        "tick_value": 0.01,
        "contract_size": 100000,
        "price_decimals": 3,
        "notes": "Major forex pair"
    },
    {
        "symbol": "SPX",
        "display_name": "S&P 500 (SPX)",
        "type": "index",
        "aliases": ["SPX", "S&P500", "US500", "S&P 500", "USA"],
        "pip_or_tick_size": 1,
        "tick_value": 1.0,
        "contract_size": 1,
        "price_decimals": 2,
        "notes": "Index CFD"
    },
    {
        "symbol": "NDX",
        "display_name": "Nasdaq 100 (NDX)",
        "type": "index",
        "aliases": ["NDX", "NAS100", "NASDAQ100", "NAS"],
        "pip_or_tick_size": 1,
        "tick_value": 1.0,
        "contract_size": 1,
        "price_decimals": 2,
        "notes": "Index CFD"
    },
    {
        "symbol": "XAUUSD",
        "display_name": "Gold (XAUUSD)",
        "type": "commodity",
        "aliases": ["XAUUSD", "GOLD", "XAU"],
        "pip_or_tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100,
        "price_decimals": 2,
        "notes": "Gold CFD"
    },
    {
        "symbol": "BTCUSD",
        "display_name": "Bitcoin (BTCUSD)",
        "type": "crypto",
        "aliases": ["BTCUSD", "BTC", "XBT"],
        "pip_or_tick_size": 0.01,
        "tick_value": 0.01,
        "contract_size": 1,
        "price_decimals": 2,
        "notes": "Crypto USD pair"
    }
]

# Generate synthetic stock universe to reach 2500+ entries
TOTAL = 2500
start = len(base)

for i in range(start+1, TOTAL+1):
    symbol = f"STK{i:04d}"
    base.append({
        "symbol": symbol,
        "display_name": f"Sample Stock {symbol}",
        "type": "stock",
        "aliases": [symbol, f"{symbol}.L"],
        "pip_or_tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 1,
        "price_decimals": 2,
        "notes": "Synthetic sample stock for testing"
    })

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open('w', encoding='utf-8') as fh:
    json.dump(base, fh, indent=2)

print(f"Wrote {len(base)} instruments to {OUT}")
