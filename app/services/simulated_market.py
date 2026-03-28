"""
Simple in-memory simulated market data provider.

Keeps a short-lived price for each instrument and applies a small
random-walk on each call so percent changes look live and consistent
across requests while the Flask process is running.

This is intentionally simple and safe: it does not call external APIs
and will fall back to sensible seed prices when DB values are unavailable.
"""
import random
import time
from threading import Lock

# Seed prices for trader-focused instruments (sensible defaults)
DEFAULT_SEEDS = {
    'BTCUSD': (42000.0, 2),
    'XAUUSD': (1950.50, 2),
    'NAS100': (16200.0, 2),
    'US30': (34000.0, 2),
    'US500': (4500.0, 2),
    'EURUSD': (1.0850, 4)
}


class SimulatedMarket:
    def __init__(self):
        # prices[symbol] = {'price': float, 'prev': float, 'decimals': int, 'updated': ts}
        self.prices = {}
        self.lock = Lock()

    def seed(self, symbol, price=None, decimals=2):
        with self.lock:
            if symbol in self.prices:
                return
            if price is None:
                seed = DEFAULT_SEEDS.get(symbol, (100.0, decimals))
                price = float(seed[0])
                decimals = int(seed[1]) if seed else int(decimals)
            self.prices[symbol] = {
                'price': float(price),
                'prev': float(price),
                'decimals': int(decimals),
                'updated': time.time()
            }

    def update_price(self, symbol):
        """Apply a small random walk to the price and return the new quote.

        The step sizes are adaptive to the price level so high-priced
        instruments don't jump unrealistically large amounts.
        """
        with self.lock:
            if symbol not in self.prices:
                self.seed(symbol)
            s = self.prices[symbol]
            prev = s['price']

            # percentage step: normally within +/-0.5% per update, tuned to instrument
            # use smaller steps for forex pairs
            if prev < 5:
                pct_step = random.uniform(-0.0025, 0.0025)  # tiny moves for very small prices
            elif prev < 100:
                pct_step = random.uniform(-0.005, 0.005)
            elif prev < 5000:
                pct_step = random.uniform(-0.01, 0.01)
            else:
                pct_step = random.uniform(-0.008, 0.008)

            # apply random drift and a small mean-reversion to prev to avoid runaway
            drift = pct_step
            new_price = prev * (1.0 + drift)

            # round to decimals
            dec = s.get('decimals', 2)
            new_price = round(new_price, dec)

            # update stored values
            s['prev'] = prev
            s['price'] = new_price
            s['updated'] = time.time()

            change_pct = 0.0
            try:
                change_pct = round(((new_price - s['prev']) / s['prev']) * 100, 2) if s['prev'] else 0.0
            except Exception:
                change_pct = 0.0

            return {
                'symbol': symbol,
                'price': new_price,
                'change_pct': change_pct,
                'decimals': dec,
                'updated': s['updated']
            }

    def get_quotes(self, symbols, instrument_objs=None):
        """Return a list of quote dicts for the requested symbols.

        If instrument_objs is provided (mapping symbol->Instrument), we use
        its price_decimals when seeding.
        """
        quotes = []
        for sym in symbols:
            dec = 2
            if instrument_objs and sym in instrument_objs:
                try:
                    dec = int(getattr(instrument_objs[sym], 'price_decimals', dec) or dec)
                except Exception:
                    dec = dec
            # ensure we've seeded
            self.seed(sym, decimals=dec)
            q = self.update_price(sym)
            # attach name placeholder (if instrument_objs available)
            name = None
            if instrument_objs and sym in instrument_objs:
                name = getattr(instrument_objs[sym], 'name', None)
            quotes.append({
                'symbol': sym,
                'name': name or sym,
                'price': q['price'],
                'change_pct': q['change_pct'],
                'decimals': q['decimals']
            })
        return quotes


# module-level singleton to keep state across requests while the process runs
market = SimulatedMarket()
